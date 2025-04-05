from flask import Flask, request, render_template
import fitz  # PyMuPDF
import os
import re
from datetime import datetime, timedelta

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# تعريف فلتر format_time (للاستخدام في Jinja إذا لزم الأمر)
def format_time(value):
    hours = int(value)
    minutes = int((value - hours) * 100)
    return f"{hours:02d}:{minutes:02d}"

app.jinja_env.filters['format_time'] = format_time

def extract_metadata(page):
    blocks = page.get_text("blocks")
    blocks_sorted = sorted(blocks, key=lambda b: b[1])
    data = {}

    for block in blocks_sorted:
        text = block[4].strip()

        if "LINES OF TIME FOR" in text and "PAGE" not in text:
            match = re.search(r"FOR\s+\((.*?)\)", text)
            if match:
                header_text = match.group(1)  # مثل: "CAPTAIN JED B777 - APR, 2025" أو "FIRST OFFICER JED B777 - APR, 2025"
                parts = header_text.split()

                # تحديد الـ Rank
                if parts[0].upper() == "FIRST" and parts[1].upper() == "OFFICER":
                    data["Rank"] = "FIRST OFFICER"
                    rank_length = 2  # عدد كلمات الـ Rank
                else:
                    data["Rank"] = "CAPTAIN"
                    rank_length = 1

                # تحديد الـ Base والـ Fleet بناءً على طول الـ Rank
                data["Base"] = parts[rank_length]      # بعد الـ Rank مباشرة
                data["Fleet"] = parts[rank_length + 1] # بعد الـ Base
                data["User Type"] = "pilot"

        elif "EFFECTIVE" in text:
            match = re.search(r"EFFECTIVE\s*(\d{2}\.\w{3}\.\d{4}) TO (\d{2}\.\w{3}\.\d{4})", text.replace("\n", " "))
            if match:
                data["Effective Period"] = f"{match.group(1)} TO {match.group(2)}"
                data["Period Start"] = match.group(1)
                data["Period End"] = match.group(2)

    return data

def generate_date_list(days, start_month, start_year):
    date_list = []
    prev_day = 0
    month = start_month
    year = start_year

    month_switch_detected = False
    for i, day in enumerate(days):
        try:
            day = int(day)
        except:
            date_list.append(None)
            continue

        # هذا هو المنطق المهم: إذا لقينا 1 بعد 28 أو 29 أو 30, نعتبرها بداية شهر جديد
        if prev_day and day == 1 and prev_day >= 28:
            month += 1
            if month > 12:
                month = 1
                year += 1
            month_switch_detected = True

        prev_day = day

        try:
            date_obj = datetime(year, month, day)
        except ValueError:
            date_obj = None

        date_list.append(date_obj.strftime("%Y-%m-%d") if date_obj else None)

    return date_list



def build_line_dict(text_block, line_number, metadata, final_end_date):
    lines = text_block.splitlines()
    period_start = datetime.strptime(metadata["Period Start"], "%d.%b.%Y")
    period_text = metadata["Effective Period"].split("TO")[0].strip()
    period_start_date = datetime.strptime(period_text, "%d.%b.%Y")
    start_month = period_start_date.month
    start_year = period_start_date.year

    header_line = next((line for line in lines if "LINE" in line and "CR" in line), "")
    credit_match = re.search(r"CR\.\s+([\d\.]+)", header_line)
    days = [int(m.group()) for m in re.finditer(r"\b\d{1,2}\b", header_line)]
    dateList = generate_date_list(days, start_month, start_year)

    type_line = lines[1] if len(lines) > 1 else ""
    line_type = type_line.split()[0] if type_line.strip() else "-"
    blk_match = re.search(r"BLK\s+([\d\.]+)", type_line)
    block_hours = blk_match.group(1).replace(".", ":") if blk_match else "00:00"

    off_line = next((line for line in lines if "NO. DP'S" in line), "")
    off_days_match = re.search(r"OFF\s+(\d+)", off_line)
    pairing_matches = list(re.finditer(r"\b\d{4}\b", off_line))

    tad_line = next((line for line in lines if line.strip().startswith("TAI") or line.strip().startswith("TAD")), "")
    duties = []
    if tad_line and "TAD" in tad_line:
        duties_raw = re.sub(r"^.*?TAD\s+[\d\.]+\s*", "", tad_line).strip()
        duties_raw_list = duties_raw.split()
        for duty in duties_raw_list:
            if duty != ':':
                duties.append(duty.replace(":", ""))

    tar_line = next((line for line in lines if line.strip().startswith("TAR")), "")
    co_match = re.search(r"C/O\s+([\d\.]+)", tar_line)

    day_positions = [m.start() for m in re.finditer(r"\b\d{1,2}\b", header_line)]
    report_positions = [m.start() for m in re.finditer(r"<", tad_line)]

    pairings = []
    period_days = [period_start + timedelta(days=i) for i in range((final_end_date - period_start).days + 1)]
    previous_date = None

    for m in pairing_matches:
        pairing = m.group()
        pos = m.start()
        closest_index = min(range(len(day_positions)), key=lambda i: abs(day_positions[i] - pos))
        start_day = days[closest_index]
        before_report = any(0 < (pos - rpos) <= 4 for rpos in report_positions)

        # نحاول نطابق رقم اليوم في كل الأيام المتاحة حتى لو كان في شهر جديد
        possible_dates = [date for date in period_days if date.day == start_day]
        start_date = None

        for date in possible_dates:
            if not previous_date or date >= previous_date:
                start_date = date
                break

        # fallback لو ما لقينا شيء
        if not start_date:
            start_date = possible_dates[0] if possible_dates else period_days[0]

        if before_report and start_day > 1:
            start_date -= timedelta(days=1)

        previous_date = start_date

        pairings.append({
            "number": pairing,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": None
        })


    return {
        "line_number": int(line_number),
        "credit": float(credit_match.group(1)) if credit_match else 0.0,
        "days": days,
        "type": line_type,
        "block_hours": block_hours,
        "off_days": int(off_days_match.group(1)) if off_days_match else 0,
        "pairings": pairings,
        "duties": duties,
        "carry_over": float(co_match.group(1)) if co_match else 0.0
    }


def extract_pairing_blocks(doc, start_page):
    blocks = []
    current = []
    capture = False
    for i in range(start_page, len(doc)):
        text = doc[i].get_text()
        for line in text.splitlines():
            if line.startswith("LINES OF TIME FOR") or line.startswith("PAGE"):
                continue
            if re.match(r"#\d{3,4}", line):
                if capture and current:
                    blocks.append("\n".join(current))
                    current = []
                capture = True
            if capture:
                current.append(line)
        if capture and current:
            blocks.append("\n".join(current))
            current = []
            capture = False
    if current:
        blocks.append("\n".join(current))
    return blocks

def match_pairings(line_dict, pairing_blocks):
    matched = []
    for p in line_dict["pairings"]:
        number = int(p["number"])
        pairing_code = f"#{number:04}" if number >= 1000 else f"#{number:03}"
        block = next((b for b in pairing_blocks if b.startswith(pairing_code)), "Not Found")
        end_date = None
        report_time = None
        if block != "Not Found":
            fd, ed = parse_pairing_times(block, p["start_date"])
            p["end_date"] = ed.strftime("%Y-%m-%dT%H:%M") if ed else None
            end_date = p["end_date"]
            lines = block.splitlines()
            if lines and "REPORT AT" in lines[0]:
                report_match = re.search(r"REPORT AT\s+(\d{2}\.\d{2})Z", lines[0])
                if report_match:
                    report_time = report_match.group(1).replace(".", ":")
        matched.append({
            "number": p["number"],
            "start_date": p["start_date"],
            "end_date": end_date,
            "first_departure": None,
            "minimum_rest": None,
            "legs": 0,
            "report_time": report_time,
            "details": block
        })
    return matched

def parse_pairing_times(block, start_date):
    day_map = {"SU": 6, "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5}
    lines = block.splitlines()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    if "<" in block:
        start_dt += timedelta(days=1)

    first_dep = last_arr = None
    for line in lines:
        if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", line):
            m = re.match(r"([A-Z]{2})\s+(?:DH)?\d{3,4}\s+\w+\s+(\d{2}\.\d{2})\s+\w+\s+(\d{2}\.\d{2})", line)
            if not m: continue
            day_code, dep, arr = m.group(1), m.group(2), m.group(3)
            target = day_map.get(day_code)
            delta = (target - start_dt.weekday() + 7) % 7
            fdate = start_dt + timedelta(days=delta)
            dep_h, dep_m = map(int, dep.split("."))
            arr_h, arr_m = map(int, arr.split("."))
            dep_dt = datetime(fdate.year, fdate.month, fdate.day, dep_h, dep_m)
            arr_dt = datetime(fdate.year, fdate.month, fdate.day, arr_h, arr_m)
            if arr_dt <= dep_dt:
                arr_dt += timedelta(days=1)
            if not first_dep:
                first_dep = dep_dt
            last_arr = arr_dt
    return first_dep, last_arr

# فلتر لتحويل التاريخ من نص إلى كائن datetime
def to_date(date_str):
    if not date_str:
        return None
    try:
        if 'T' in date_str:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        print(f"Error parsing date: {date_str}, {e}")
        return None

# فلتر لتحديد يوم الأسبوع
def day_of_week(day):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return days[(day + 5) % 7]  # افتراض 1 أبريل 2025 الثلاثاء

app.jinja_env.filters['to_date'] = to_date
app.jinja_env.filters['day_of_week'] = day_of_week

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files["file"]
        if file and file.filename.endswith(".pdf"):
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
            file.save(filepath)
            doc = fitz.open(filepath)
            metadata = extract_metadata(doc[0])

            all_lines = []
            line_pages = []
            period_start = datetime.strptime(metadata["Period Start"], "%d.%b.%Y")
            period_end = datetime.strptime(metadata["Period End"], "%d.%b.%Y")
            # استخدام period_end كقيمة أولية لـ final_end_date
            temp_final_end_date = period_end + timedelta(days=10)  # إضافة 10 أيام كافتراض مبدئي

            for i in range(1, len(doc)):
                text = doc[i].get_text()
                if re.search(r"LINE\s+\d{3}", text):
                    line_pages.append(i)
                    blocks = re.split(r"(?=LINE\s+\d{3})", text)
                    for block in blocks:
                        match = re.search(r"LINE\s+(\d{3})", block)
                        if not match:
                            continue
                        number = match.group(1)
                        line_dict = build_line_dict(block, number, metadata, temp_final_end_date)
                        all_lines.append(line_dict)

            last_line_page = max(line_pages) if line_pages else 1
            pairing_blocks = extract_pairing_blocks(doc, last_line_page + 1)

            all_pairings = []
            line_stats = []
            total_legs_all = 0
            total_deadheads_all = 0
            total_four_legs_all = 0
            total_pairings_all = 0

            for line in all_lines:
                matched = match_pairings(line, pairing_blocks)
                line_total_legs = 0
                line_deadheads = 0
                line_four_legs = 0
                destinations = set()
                layovers = []
                pairings_count = len(matched)

                for idx, p in enumerate(matched):
                    if p["details"] != "Not Found":
                        fd, ed = parse_pairing_times(p["details"], p["start_date"])
                        p["first_departure"] = fd.strftime("%Y-%m-%dT%H:%M") if fd else None
                        if not p["end_date"] and ed:
                            p["end_date"] = ed.strftime("%Y-%m-%dT%H:%M")
                        legs = [l for l in p["details"].splitlines() if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", l)]
                        p["legs"] = len(legs)
                        line_total_legs += p["legs"]
                        line_deadheads += len([l for l in p["details"].splitlines() if "DH" in l])
                        
                        lines = p["details"].splitlines()
                        consecutive_legs = []
                        for line_text in lines:
                            if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", line_text):
                                consecutive_legs.append(line_text)
                                arr_match = re.search(r"\d{2}\.\d{2}\s+(\w{3})\s+\d{2}\.\d{2}", line_text)
                                if arr_match:
                                    arr_city = arr_match.group(1)
                                    if arr_city != metadata["Base"]:
                                        destinations.add(arr_city)
                            elif "LAYOVER" in line_text and consecutive_legs:
                                if len(consecutive_legs) >= 4:
                                    line_four_legs += 1
                                consecutive_legs = []
                                layover_match = re.search(r"LAYOVER\s+(\w{3})\s+(\d{2}\.\d{2})", line_text)
                                if layover_match:
                                    city = layover_match.group(1)
                                    time = layover_match.group(2)
                                    hours, minutes = map(int, time.split("."))
                                    layovers.append(f"{city}: {hours:02d}:{minutes:02d}")
                        if len(consecutive_legs) >= 4:
                            line_four_legs += 1

                for i in range(len(matched) - 1):
                    if matched[i]["end_date"] and matched[i+1]["first_departure"]:
                        rest = datetime.strptime(matched[i+1]["first_departure"], "%Y-%m-%dT%H:%M") - datetime.strptime(matched[i]["end_date"], "%Y-%m-%dT%H:%M")
                        mins = int(rest.total_seconds() // 60)
                        h, m = divmod(mins, 60)
                        matched[i]["minimum_rest"] = f"{h:02d}:{m:02d}" if h <= 48 else "More than 48 Hrs"
                if matched:
                    matched[-1]["minimum_rest"] = "—"

                min_rest = "—"
                rest_times = []
                for pairing in matched:
                    if pairing["minimum_rest"] and pairing["minimum_rest"] != "—" and "More than" not in pairing["minimum_rest"]:
                        h, m = map(int, pairing["minimum_rest"].split(":"))
                        total_minutes = h * 60 + m
                        rest_times.append(total_minutes)
                if rest_times:
                    min_minutes = min(rest_times)
                    h, m = divmod(min_minutes, 60)
                    min_rest = f"{h:02d}:{m:02d}"

                all_pairings.extend(matched)
                line_stats.append({
                    "line_number": line["line_number"],
                    "type": line["type"],
                    "block_hours": line["block_hours"],
                    "off_days": line["off_days"],
                    "carry_over": line["carry_over"],
                    "total_legs": line_total_legs,
                    "four_legs_count": line_four_legs,
                    "deadheads": line_deadheads,
                    "destinations": list(destinations),
                    "arrival_destinations": list(destinations),
                    "layovers": layovers,
                    "pairings_count": pairings_count,
                    "pairings": matched,
                    "minimum_rest": min_rest,
                    "duties": line.get("duties", [])
                })

                total_legs_all += line_total_legs
                total_deadheads_all += line_deadheads
                total_four_legs_all += line_four_legs
                total_pairings_all += pairings_count

            # حساب final_end_date بعد استخراج كل البيانات
            days_in_period = (period_end - period_start).days + 1
            max_end_date = period_end
            for line in line_stats:
                for pairing in line["pairings"]:
                    if pairing["end_date"]:
                        end_date = datetime.strptime(pairing["end_date"], "%Y-%m-%dT%H:%M")
                        if end_date > max_end_date:
                            max_end_date = end_date

            if max_end_date > period_end:
                next_month_start = period_end.replace(day=1) + timedelta(days=32)
                next_month_start = next_month_start.replace(day=1)
                max_allowed_date = next_month_start + timedelta(days=9)
                final_end_date = max(max_end_date, max_allowed_date)
            else:
                final_end_date = period_end

            days_in_period = (final_end_date - period_start).days + 1

            date_list = []
            for day in range(days_in_period):
                current_date = period_start + timedelta(days=day)
                date_list.append({
                    "day": current_date.day,
                    "month": current_date.strftime('%b'),
                    "weekday": current_date.strftime('%a'),
                    "is_first_of_month": current_date.day == 1
                })

            month_name = period_start.strftime("%B")
            year = period_start.year

            total_stats = (
                f"Total Legs Across All Lines: {total_legs_all}\n"
                f"Number of 4-Leg Sequences: {total_four_legs_all}\n"
                f"Total Deadheads: {total_deadheads_all}\n"
                f"Total Pairings Across All Lines: {total_pairings_all}"
            )

            return render_template(
                "index.html",
                lines=line_stats,
                success_message="Data extracted successfully",
                days_in_period=days_in_period,
                month_name=month_name,
                year=year,
                date_list=date_list,
                period_start=period_start.strftime("%Y-%m-%d"),
                metadata=metadata
            )

    return render_template(
        "index.html",
        days_in_period=0,
        date_list=[],
        month_name="",
        year="",
        period_start="",
        metadata={}
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)