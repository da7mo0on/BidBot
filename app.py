from flask import Flask, request, render_template
from flask_session import Session
import fitz  # PyMuPDF
import os
import re
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# إعدادات Flask-Session
app.config['SECRET_KEY'] = 'bidbot-engal-2025-super-secret'  # سلسلة عشوائية لتأمين الجلسات
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_FILE_THRESHOLD'] = 100
Session(app)

# تنظيف ملفات الجلسات المنتهية
def clean_old_sessions():
    session_dir = app.config.get('SESSION_FILE_DIR', 'flask_session')
    if os.path.exists(session_dir):
        for filename in os.listdir(session_dir):
            file_path = os.path.join(session_dir, filename)
            try:
                mtime = os.path.getmtime(file_path)
                file_age = datetime.now() - datetime.fromtimestamp(mtime)
                if file_age > timedelta(minutes=30):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error cleaning session file {file_path}: {e}")

with app.app_context():
    clean_old_sessions()

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

        if "LINES OF TIME FOR" in text.upper() and "PAGE" not in text:
            match = re.search(r"FOR\s+\((.*?)\)", text)
            if match:
                header_text = match.group(1)  # مثل: "ECONOMY CABIN ATTENDANT JED 33 - APR, 2025"
                parts = header_text.split(" - ")
                period = parts[-1].strip()  # مثل: "APR, 2025"

                # تقسيم الجزء الأول إلى كلمات
                header_parts = parts[0].split()

                # تحديد نوع المستخدم
                if header_parts and (header_parts[0].upper() == "CAPTAIN" or (len(header_parts) > 1 and header_parts[0].upper() == "FIRST" and header_parts[1].upper() == "OFFICER")):
                    data["User Type"] = "pilot"
                    # معالجة الطيارين
                    if header_parts[0].upper() == "FIRST" and header_parts[1].upper() == "OFFICER":
                        data["Rank"] = "FIRST OFFICER"
                        rank_length = 2
                    else:
                        data["Rank"] = "CAPTAIN"
                        rank_length = 1
                    # البيس هو الكلمة التالية بعد الرانك
                    data["Base"] = header_parts[rank_length]
                    # الفليت هو ما تبقى (قد يكون كلمتين مثل "9 Z")
                    fleet_start = rank_length + 1
                    fleet_end = fleet_start + 1
                    if fleet_end < len(header_parts) and re.match(r"[A-Z]+", header_parts[fleet_end]):
                        data["Fleet"] = f"{header_parts[fleet_start]} {header_parts[fleet_end]}"
                    else:
                        data["Fleet"] = header_parts[fleet_start]
                else:
                    # افتراض أن أي شيء آخر هو cabin_crew
                    data["User Type"] = "cabin_crew"
                    # البحث عن الفليت من النهاية (لأنه دائمًا في النهاية قبل الـ Period)
                    fleet_index = -1
                    for i in range(len(header_parts) - 1, -1, -1):
                        part = header_parts[i]
                        # نمط الفليت: رقم فقط (مثل "33") أو رقم متبوع بحرف (مثل "9 Z")
                        if re.match(r"\d+$|\d+\s*[A-Z]+", part.replace(" ", "")):
                            fleet_index = i
                            break
                    if fleet_index == -1:
                        # إذا لم يتم العثور على فليت، نفترض أنه آخر كلمتين
                        fleet_index = len(header_parts) - 2

                    # التحقق مما إذا كان الفليت مكون من كلمتين (مثل "9 Z")
                    fleet_start = fleet_index
                    fleet_end = fleet_start + 1
                    if fleet_end < len(header_parts) and re.match(r"[A-Z]+", header_parts[fleet_end]):
                        data["Fleet"] = f"{header_parts[fleet_start]} {header_parts[fleet_end]}"
                        base_index = fleet_start - 1
                    else:
                        data["Fleet"] = header_parts[fleet_start]
                        base_index = fleet_start - 1

                    # البيس هو الكلمة قبل الفليت
                    data["Base"] = header_parts[base_index] if base_index >= 0 else "Unknown"
                    # الرانك هو كل الكلمات قبل البيس
                    data["Rank"] = " ".join(header_parts[:base_index]) or "CABIN CREW"

                data["Period"] = period

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

def extract_pairing_destination(duties, pairing_start_date, period_start, base, before_report):
    period_start_dt = datetime.strptime(period_start, "%d.%b.%Y")
    pairing_start_dt = datetime.strptime(pairing_start_date, "%Y-%m-%d")
    
    day_offset = (pairing_start_dt - period_start_dt).days
    
    if before_report and pairing_start_dt.day > 1:
        day_offset += 1
    
    if day_offset < 0 or day_offset >= len(duties):
        return {"destination": "Unknown", "next_destination": None}
    
    initial_destination = duties[day_offset]
    destination = initial_destination
    
    # التأكد من تخطي '<' إذا كانت الدوتي الأولية
    if destination == '<' and day_offset + 1 < len(duties):
        day_offset += 1
        destination = duties[day_offset]
        initial_destination = destination
    
    # التحقق من الوجهة إذا كانت '-' متبوعة بـ base
    consecutive_minus_base = False
    if destination == '-' and day_offset + 1 < len(duties):
        next_day_duty = duties[day_offset + 1]
        if next_day_duty == base:
            consecutive_minus_base = True
    
    # التحقق من الوجهة إذا كانت base متتالية
    consecutive_base = False
    if destination == base and day_offset + 1 < len(duties):
        next_day_duty = duties[day_offset + 1]
        if next_day_duty == base:
            consecutive_base = True
    
    # تخطي '-' أو base إذا لم يكن هناك consecutive_base أو consecutive_minus_base
    if not (consecutive_base or consecutive_minus_base):
        while (destination == "-" or destination == base) and day_offset + 1 < len(duties):
            day_offset += 1
            destination = duties[day_offset]
    
    # إذا كانت الوجهة لا تزال '-' أو base (وليس consecutive_base)، نرجع "Unknown"
    if destination == "-" or (destination == base and not consecutive_base):
        return {"destination": "Unknown", "next_destination": None}
    
    # إذا كان هناك consecutive_base أو consecutive_minus_base، نرجع الوجهة الأولية
    if consecutive_base or consecutive_minus_base:
        destination = initial_destination
    
    # استخراج الوجهة التالية (إن وجدت)
    next_destination = None
    next_offset = day_offset + 1
    if next_offset < len(duties):
        next_destination = duties[next_offset]
        # تخطي '-' أو base في الوجهة التالية
        while (next_destination == "-" or next_destination == base) and next_offset + 1 < len(duties):
            next_offset += 1
            next_destination = duties[next_offset]
        if next_destination == "-" or next_destination == base:
            next_destination = None

    return {
        "destination": destination,
        "next_destination": next_destination
    }


def build_line_dict(text_block, line_number, metadata, final_end_date):
    lines = text_block.splitlines()
    period_start = datetime.strptime(metadata["Period Start"], "%d.%b.%Y")
    period_text = metadata["Effective Period"].split("TO")[0].strip()
    period_start_date = datetime.strptime(period_text, "%d.%b.%Y")
    start_month = period_start_date.month
    start_year = period_start_date.year

    header_line = next((line for line in lines if "LINE" in line and "CR" in line), "")
    credit_match = re.search(r"CR\.\s+([\d\.]+)", header_line)

    if metadata["User Type"] == "cabin_crew":
        credit_match_pos = re.search(r"CR\. \d{2}\.\d{2}", header_line)
        start_pos = credit_match_pos.end() if credit_match_pos else 0
        days = []
        day_positions = []
        for m in re.finditer(r"\b\d{1,2}\b", header_line[start_pos:]):
            day = int(m.group())
            if 1 <= day <= 31 or day in [1, 2, 3, 4, 5]:
                days.append(day)
                day_positions.append(m.start() + start_pos)
    else:
        days = [int(m.group()) for m in re.finditer(r"\b\d{1,2}\b", header_line)]
        day_positions = [m.start() for m in re.finditer(r"\b\d{1,2}\b", header_line)]

    dateList = generate_date_list(days, start_month, start_year)

    type_line = lines[1] if len(lines) > 1 else ""
    line_type = type_line.split()[0] if type_line.strip() else "-"
    blk_match = re.search(r"BLK\s+([\d\.]+)", type_line)
    block_hours = blk_match.group(1).replace(".", ":") if blk_match else "00:00"

    off_line = next((line for line in lines if "NO. DP'S" in line), "")
    off_days_match = re.search(r"OFF\s+(\d+)", off_line)
    if metadata["User Type"] == "cabin_crew":
        pairing_matches = list(re.finditer(r"\b\d{3}\b", off_line))
    else:
        pairing_matches = list(re.finditer(r"\b\d{4}\b", off_line))

    tad_line = next((line for line in lines if line.strip().startswith("TAI") or line.strip().startswith("TAD")), "")
    tar_line = next((line for line in lines if line.strip().startswith("TAR")), "")
    duties = []

    if metadata["User Type"] == "cabin_crew":
        if tad_line and "TAD" in tad_line:
            duties_raw = re.sub(r"^.*?TAD\s+[\d\.]+\s*", "", tad_line).strip()
            duties_raw_list = duties_raw.split()
            for duty in duties_raw_list:
                if duty != ':':
                    duties.append(duty.replace(":", ""))
        if not duties:
            if tar_line and "C/O" in tar_line:
                duties_raw = re.sub(r"^.*?C/O\s+[\d\.]+\s*", "", tar_line).strip()
                duties_raw_list = duties_raw.split()
                for duty in duties_raw_list:
                    if duty != ':':
                        duties.append(duty.replace(":", ""))
    else:
        if tad_line and "TAD" in tad_line:
            duties_raw = re.sub(r"^.*?TAD\s+[\d\.]+\s*", "", tad_line).strip()
            duties_raw_list = duties_raw.split()
            for duty in duties_raw_list:
                if duty != ':':
                    duties.append(duty.replace(":", ""))

    co_match = re.search(r"C/O\s+([\d\.]+)", tar_line)
    report_positions = [m.start() for m in re.finditer(r"<", tad_line)]

    pairings = []
    period_days = [period_start + timedelta(days=i) for i in range((final_end_date - period_start).days + 1)]
    previous_date = None

    for m in pairing_matches:
        pairing = m.group()
        pos = m.start() - 1
        closest_index = min(range(len(day_positions)), key=lambda i: abs(day_positions[i] - pos))
        start_day = days[closest_index]

        before_report = any(0 < (pos - rpos) <= 4 for rpos in report_positions)

        possible_dates = [date for date in period_days if date.day == start_day]
        start_date = None

        for date in possible_dates:
            if not previous_date or date >= previous_date:
                start_date = date
                break

        if not start_date:
            start_date = possible_dates[0] if possible_dates else period_days[0]

        # ✅ تعديل: التحقق من '<' مع التعامل مع الانتقال بين الشهور بشكل مرن
        day_offset = (start_date - period_start).days
        adjusted_for_less = False
        if metadata["User Type"] == "pilot":
            if 0 <= day_offset < len(duties):
                if day_offset > 0 and duties[day_offset - 1].find('<') != -1 and start_date.day == 1:
                    # التعامل مع نهاية الشهر السابق
                    start_date = start_date - timedelta(days=1)
                    adjusted_for_less = True
                elif day_offset > 0 and duties[day_offset - 1].find('<') != -1:
                    start_date -= timedelta(days=1)
                    adjusted_for_less = True
        else:  # للمضيفين (cabin_crew)
            if 0 <= day_offset < len(duties):
                if day_offset + 1 < len(duties) and duties[day_offset] == '<' and start_date.day == 1:
                    # التحقق إذا كان البيرنق في يوم 1 من الشهر الجديد
                    last_day_of_prev_month = (start_date.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=1)
                    start_date = last_day_of_prev_month.replace(day=last_day_of_prev_month.day)
                    adjusted_for_less = True
                elif day_offset > 0 and duties[day_offset - 1] == '<':
                    start_date -= timedelta(days=1)
                    adjusted_for_less = True

        if before_report and start_date.day > 1 and not adjusted_for_less:
            start_date -= timedelta(days=1)

        previous_date = start_date

        # استخراج الوجهة والوجهة التالية
        destination_info = extract_pairing_destination(
            duties, 
            start_date.strftime("%Y-%m-%d"), 
            metadata["Period Start"], 
            metadata["Base"], 
            before_report
        )

        pairings.append({
            "number": pairing,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": None,
            "destination": destination_info["destination"],
            "next_destination": destination_info["next_destination"],
            "before_report": before_report,
            "adjusted_for_less": adjusted_for_less
        })

    result = {
        "line_number": int(line_number),
        "credit": float(credit_match.group(1)) if credit_match else 0.0,
        "days": days,
        "type": line_type,
        "block_hours": block_hours,
        "off_days": int(off_days_match.group(1)) if off_days_match else 0,
        "pairings": pairings,
        "duties": duties,
        "carry_over": float(co_match.group(1)) if co_match else 0.0,
        "user_type": metadata.get("User Type", "pilot"),
        "Period Start": metadata["Period Start"],
        "Base": metadata["Base"]
    }
    return result


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
                    # التحقق مما إذا كان البلوك مقلوبًا
                    block_text = "\n".join(current)
                    if is_block_inverted(block_text):
                        # تصحيح البلوك إذا كان مقلوبًا
                        corrected_block = correct_block_order(block_text)
                        blocks.append(corrected_block)
                    else:
                        # إضافة البلوك كما هو إذا لم يكن مقلوبًا
                        blocks.append(block_text)
                    current = []
                capture = True
            if capture:
                current.append(line)
        if capture and current:
            block_text = "\n".join(current)
            if is_block_inverted(block_text):
                corrected_block = correct_block_order(block_text)
                blocks.append(corrected_block)
            else:
                blocks.append(block_text)
            current = []
            capture = False
    if current:
        block_text = "\n".join(current)
        if is_block_inverted(block_text):
            corrected_block = correct_block_order(block_text)
            blocks.append(corrected_block)
        else:
            blocks.append(block_text)
    return blocks

def is_block_inverted(block):
    """
    Check if a pairing block is inverted by checking if the first flight does not start from the Base
    and the second flight starts from the Base.
    Returns True if the block is inverted, False otherwise.
    """
    lines = block.splitlines()
    if not lines:
        return False

    # جمع أول رحلتين (مع تخطي LAYOVER إذا وجد)
    flight_origins = []
    flight_count = 0
    for line in lines:
        if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", line):
            flight_count += 1
            # استخراج نقطة المغادرة (المدينة الأولى بعد توقيت المغادرة)
            match = re.search(r"\d{2}\.\d{2}\s+([A-Z]{3})\s+\d{2}\.\d{2}", line)
            if match:
                origin = match.group(1)  # نقطة المغادرة (مثل JED أو LHE)
                flight_origins.append(origin)
            else:
                flight_origins.append(None)
            if flight_count == 2:  # توقف بعد أول رحلتين
                break
        elif "LAYOVER" in line:
            continue  # تخطي LAYOVER

    # التحقق مما إذا كان البلوك مقلوبًا
    if len(flight_origins) < 2:
        return False  # إذا لم يكن هناك رحلتان على الأقل، لا يمكن أن يكون مقلوبًا

    first_origin = flight_origins[0]
    second_origin = flight_origins[1]
    # يجب إضافة Base إلى line_dict في build_line_dict، لكن نفترض أنه موجود هنا
    # نفترض أن Base هو JED (سيتم تمريره لاحقًا)
    base = "JED"  # سيتم استبداله بـ line_dict["Base"] عند التكامل مع match_pairings

    # الشرط: أول رحلة لا تبدأ من الـ Base، والرحلة الثانية تبدأ من الـ Base
    if first_origin and second_origin:
        if first_origin != base and second_origin == base:
            return True  # البلوك مقلوب
    return False

def correct_block_order(block):
    """
    Correct an inverted pairing block by moving the first flight (which is the last chronologically)
    to the position just before the CREDIT line. Keeps all other lines unchanged.
    """
    lines = block.splitlines()
    if not lines:
        return block

    # فصل الأسطر
    flight_lines = []
    other_lines = []
    credit_line = None
    first_flight = None

    for line in lines:
        if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", line):
            if not first_flight:  # الرحلة الأولى (الخاطئة)
                first_flight = line
            else:
                flight_lines.append(line)  # باقي الرحلات
        elif "CREDIT:" in line:
            credit_line = line
        else:
            other_lines.append(line)

    # إعادة بناء البلوك مع نقل الرحلة الأولى قبل CREDIT
    corrected_lines = []
    # أضف الأسطر الأخرى في الأعلى (مثل REPORT AT) وأسطر الرحلات الأخرى
    for line in other_lines:
        if line.startswith("#"):
            corrected_lines.append(line)
    corrected_lines.extend(flight_lines)  # أضف باقي الرحلات
    # أضف الأسطر الأخرى بين الرحلات وسطر CREDIT (مثل LAYOVER)
    for line in other_lines:
        if not line.startswith("#"):
            corrected_lines.append(line)
    # أضف الرحلة الأولى (الخاطئة) قبل CREDIT
    if first_flight:
        corrected_lines.append(first_flight)
    # أضف سطر CREDIT في النهاية
    if credit_line:
        corrected_lines.append(credit_line)

    return "\n".join(corrected_lines)

def match_pairings(line_dict, pairing_blocks, pairing_index=None):
    matched = []
    pairing_cache = {}

    for p in line_dict["pairings"]:
        number = int(p["number"])
        key = (number, p["start_date"], p["destination"])

        if key in pairing_cache:
            matched.append(pairing_cache[key])
            continue

        if line_dict.get("user_type") == "pilot":
            pairing_code = f"#{number:04}" if number >= 1000 else f"#{number:03}"
            block = next((b for b in pairing_blocks if b.startswith(pairing_code)), "Not Found")
            if block == "Not Found":
                continue
            lines = block.splitlines()
            report_time = None
            if lines and "REPORT AT" in lines[0]:
                report_match = re.search(r"REPORT AT\s+(\d{2}\.\d{2})Z", lines[0])
                if report_match:
                    report_time = report_match.group(1).replace(".", ":")
            result = {
                "number": p["number"],
                "start_date": p["start_date"],
                "end_date": None,
                "first_departure": None,
                "minimum_rest": None,
                "legs": 0,
                "report_time": report_time,
                "details": block,
                "destination": p["destination"]
            }
            pairing_cache[key] = result
            matched.append(result)
            continue

        if pairing_index is not None:
            pairing_code = f"{number:03}"
            start_dt = datetime.strptime(p["start_date"], "%Y-%m-%d")
            before_report = p.get("before_report", False)
            if before_report:
                adjusted_dt = start_dt + timedelta(days=1)
            else:
                adjusted_dt = start_dt
            day_code = adjusted_dt.strftime("%a").upper()[:2]
            dest = p["destination"]

            ignore_destination = False
            if line_dict.get("user_type") == "cabin_crew":
                duties = line_dict.get("duties", [])
                period_start_dt = datetime.strptime(line_dict["Period Start"], "%d.%b.%Y")
                pairing_start_dt = datetime.strptime(p["start_date"], "%Y-%m-%d")
                day_offset = (pairing_start_dt - period_start_dt).days
                if before_report and pairing_start_dt.day > 1:
                    day_offset += 1
                base = line_dict.get("Base", "")
                if day_offset < len(duties) and day_offset + 1 < len(duties):
                    current_duty = duties[day_offset]
                    next_duty = duties[day_offset + 1]
                    # التحقق من base متتالية
                    if current_duty == base and next_duty == base:
                        ignore_destination = True
                    # التحقق من '-' متبوع بـ base
                    if current_duty == "-" and next_duty == base:
                        ignore_destination = True

            special_compare = False
            dest_first = dest_last = None
            if line_dict.get("user_type") == "cabin_crew" and "<" in dest:
                special_compare = True
                dest_first = dest[0]
                dest_last = dest[-1]

            if ignore_destination:
                possible_blocks = [
                    (key, block) for key, block in pairing_index.items()
                    if key[0] == pairing_code and key[1] == day_code
                ]
                block = possible_blocks[0][1] if possible_blocks else None
            elif special_compare:
                possible_blocks = [
                    (key, block) for key, block in pairing_index.items()
                    if key[0] == pairing_code and key[1] == day_code and
                    len(key[2]) >= 2 and key[2][0] == dest_first and key[2][-1] == dest_last
                ]
                block = possible_blocks[0][1] if possible_blocks else None
            else:
                index_key = (pairing_code, day_code, dest)
                block = pairing_index.get(index_key)

            if block:
                lines = block.splitlines()
                fd, ed = parse_pairing_times(block, p["start_date"])
                report_time = None
                if lines and "REPORT AT" in lines[0]:
                    report_match = re.search(r"REPORT AT\s+(\d{2}\.\d{2})Z", lines[0])
                    if report_match:
                        report_time = report_match.group(1).replace(".", ":")

                result = {
                    "number": p["number"],
                    "start_date": p["start_date"],
                    "end_date": ed.strftime("%Y-%m-%dT%H:%M") if ed else None,
                    "first_departure": fd.strftime("%Y-%m-%dT%H:%M") if fd else None,
                    "minimum_rest": None,
                    "legs": len([l for l in lines if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", l)]),
                    "report_time": report_time,
                    "details": block,
                    "destination": dest
                }
            else:
                continue

            pairing_cache[key] = result
            matched.append(result)
            continue

        expected_dest = p["destination"]
        start_dt = datetime.strptime(p["start_date"], "%Y-%m-%d")
        before_report = p.get("before_report", False)
        if before_report:
            adjusted_dt = start_dt + timedelta(days=1)
        else:
            adjusted_dt = start_dt
        expected_day_code = adjusted_dt.strftime("%a").upper()[:2]

        ignore_destination = False
        if line_dict.get("user_type") == "cabin_crew":
            duties = line_dict.get("duties", [])
            period_start_dt = datetime.strptime(line_dict["Period Start"], "%d.%b.%Y")
            pairing_start_dt = datetime.strptime(p["start_date"], "%Y-%m-%d")
            day_offset = (pairing_start_dt - period_start_dt).days
            if before_report and pairing_start_dt.day > 1:
                day_offset += 1
            base = line_dict.get("Base", "")
            if day_offset < len(duties) and day_offset + 1 < len(duties):
                current_duty = duties[day_offset]
                next_duty = duties[day_offset + 1]
                # التحقق من base متتالية
                if current_duty == base and next_duty == base:
                    ignore_destination = True
                # التحقق من '-' متبوع بـ base
                if current_duty == "-" and next_duty == base:
                    ignore_destination = True

        special_compare = False
        expected_dest_first = expected_dest_last = None
        if line_dict.get("user_type") == "cabin_crew" and "<" in expected_dest:
            special_compare = True
            expected_dest_first = expected_dest[0]
            expected_dest_last = expected_dest[-1]

        matching_blocks = []
        for block in pairing_blocks:
            lines = block.splitlines()
            if lines and re.match(rf"#{number:03}\b", lines[0]):
                matching_blocks.append(block)

        found = False
        for block in matching_blocks:
            lines = block.splitlines()
            first_flight_line = None
            first_flight_dest = None
            first_flight_daycode = None

            if len(lines) >= 2:
                line = lines[1]
                flight_match = re.search(
                    r"\b([A-Z]{2})\s+(?:DH)?(\d{3,4})\s+[A-Z0-9]{2,3}\s+\d{2}\.\d{2}\s+([A-Z]{3})\s+\d{2}\.\d{2}\s+([A-Z]{3})\s+\d{2}\.\d{2}",
                    line
                )
                if flight_match:
                    first_flight_daycode = flight_match.group(1)
                    first_flight_dest = flight_match.group(4)
                    first_flight_line = line

            if ignore_destination:
                match_condition = first_flight_daycode == expected_day_code
            elif special_compare:
                if first_flight_dest and len(first_flight_dest) >= 2:
                    match_condition = (first_flight_daycode == expected_day_code and
                                       first_flight_dest[0] == expected_dest_first and
                                       first_flight_dest[-1] == expected_dest_last)
                else:
                    match_condition = False
            else:
                match_condition = first_flight_daycode == expected_day_code and first_flight_dest == expected_dest

            if match_condition:
                fd, ed = parse_pairing_times(block, p["start_date"])
                end_date = ed.strftime("%Y-%m-%dT%H:%M") if ed else None
                report_time = None
                if lines and "REPORT AT" in lines[0]:
                    report_match = re.search(r"REPORT AT\s+(\d{2}\.\d{2})Z", lines[0])
                    if report_match:
                        report_time = report_match.group(1).replace(".", ":")

                result = {
                    "number": p["number"],
                    "start_date": p["start_date"],
                    "end_date": end_date,
                    "first_departure": fd.strftime("%Y-%m-%dT%H:%M") if fd else None,
                    "minimum_rest": None,
                    "legs": len([l for l in lines if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", l)]),
                    "report_time": report_time,
                    "details": block,
                    "destination": p["destination"]
                }

                pairing_cache[key] = result
                matched.append(result)
                found = True
                break

        if not found:
            continue

    return matched


def parse_pairing_times(block, start_date, adjusted_for_less=False):
    day_map = {"SU": 6, "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5}
    lines = block.splitlines()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    # ✅ تعديل: عدم إضافة يوم إذا تم التصحيح مسبقًا
    if "<" in block and not adjusted_for_less:
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

def get_first_layover_destination(block):
    """
    Extract the first layover destination from a pairing block.
    Returns the destination (e.g., 'NUM') or None if not found.
    """
    lines = block.splitlines()
    for line in lines:
        if "LAYOVER" in line:
            layover_match = re.search(r"LAYOVER\s+(\w{3})\s+\d{2}\.\d{2}", line)
            if layover_match:
                return layover_match.group(1)  # e.g., 'NUM'
    return None

def match_pairings(line_dict, pairing_blocks, pairing_index=None, use_layover_destination=False):
    matched = []
    pairing_cache = {}

    for p in line_dict["pairings"]:
        number = int(p["number"])
        key = (number, p["start_date"], p["destination"])

        if key in pairing_cache:
            matched.append(pairing_cache[key])
            continue

        if line_dict.get("user_type") == "pilot":
            pairing_code = f"#{number:04}" if number >= 1000 else f"#{number:03}"
            block = next((b for b in pairing_blocks if b.startswith(pairing_code)), "Not Found")
            if block == "Not Found":
                continue
            lines = block.splitlines()
            report_time = None
            if lines and "REPORT AT" in lines[0]:
                report_match = re.search(r"REPORT AT\s+(\d{2}\.\d{2})Z", lines[0])
                if report_match:
                    report_time = report_match.group(1).replace(".", ":")
            result = {
                "number": p["number"],
                "start_date": p["start_date"],
                "end_date": None,
                "first_departure": None,
                "minimum_rest": None,
                "legs": 0,
                "report_time": report_time,
                "details": block,
                "destination": p["destination"]
            }
            pairing_cache[key] = result
            matched.append(result)
            continue

        if pairing_index is not None:
            pairing_code = f"{number:03}"
            start_dt = datetime.strptime(p["start_date"], "%Y-%m-%d")
            before_report = p.get("before_report", False)
            if before_report:
                adjusted_dt = start_dt + timedelta(days=1)
            else:
                adjusted_dt = start_dt
            day_code = adjusted_dt.strftime("%a").upper()[:2]
            prev_day_dt = adjusted_dt - timedelta(days=1)
            prev_day_code = prev_day_dt.strftime("%a").upper()[:2]
            dest = p["destination"]
            next_dest = p.get("next_destination")
            adjusted_for_less = p.get("adjusted_for_less", False)

            ignore_destination = False
            if line_dict.get("user_type") in ["cabin_crew", "pilot"]:
                duties = line_dict.get("duties", [])
                period_start_dt = datetime.strptime(line_dict["Period Start"], "%d.%b.%Y")
                pairing_start_dt = datetime.strptime(p["start_date"], "%Y-%m-%d")
                day_offset = (pairing_start_dt - period_start_dt).days
                if before_report and pairing_start_dt.day > 1:
                    day_offset += 1
                base = line_dict.get("Base", "")
                if day_offset < len(duties) and day_offset + 1 < len(duties):
                    current_duty = duties[day_offset]
                    next_duty = duties[day_offset + 1]
                    if current_duty == base and next_duty == base:
                        ignore_destination = True
                    if current_duty == "-" and next_duty == base:
                        ignore_destination = True

            special_compare = False
            dest_first = dest_last = None
            if line_dict.get("user_type") in ["cabin_crew", "pilot"] and "<" in dest:
                special_compare = True
                dest_first = dest[0]
                dest_last = dest[-1]

            if ignore_destination:
                possible_blocks = [
                    (key, block) for key, block in pairing_index.items()
                    if key[0] == pairing_code and key[1] == day_code
                ]
                block = possible_blocks[0][1] if possible_blocks else None
            elif special_compare:
                possible_blocks = [
                    (key, block) for key, block in pairing_index.items()
                    if key[0] == pairing_code and key[1] == day_code and
                    len(key[2]) >= 2 and key[2][0] == dest_first and key[2][-1] == dest_last
                ]
                block = possible_blocks[0][1] if possible_blocks else None
            else:
                index_key = (pairing_code, day_code, dest)
                block = pairing_index.get(index_key)
                if block is None:
                    index_key = (pairing_code, prev_day_code, dest)
                    block = pairing_index.get(index_key)
                if block is None and next_dest:
                    index_key = (pairing_code, day_code, next_dest)
                    block = pairing_index.get(index_key)
                if block is None and next_dest:
                    index_key = (pairing_code, prev_day_code, next_dest)
                    block = pairing_index.get(index_key)
                if block is None and use_layover_destination:
                    possible_blocks = [
                        (key, block) for key, block in pairing_index.items()
                        if key[0] == pairing_code and (key[1] == day_code or key[1] == prev_day_code)
                    ]
                    if possible_blocks:
                        for _, potential_block in possible_blocks:
                            layover_dest = get_first_layover_destination(potential_block)
                            if layover_dest and (layover_dest == dest or (next_dest and layover_dest == next_dest)):
                                block = potential_block
                                break

            if block:
                lines = block.splitlines()
                fd, ed = parse_pairing_times(block, p["start_date"], adjusted_for_less)
                report_time = None
                if lines and "REPORT AT" in lines[0]:
                    report_match = re.search(r"REPORT AT\s+(\d{2}\.\d{2})Z", lines[0])
                    if report_match:
                        report_time = report_match.group(1).replace(".", ":")

                result = {
                    "number": p["number"],
                    "start_date": p["start_date"],
                    "end_date": ed.strftime("%Y-%m-%dT%H:%M") if ed else None,
                    "first_departure": fd.strftime("%Y-%m-%dT%H:%M") if fd else None,
                    "minimum_rest": None,
                    "legs": len([l for l in lines if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", l)]),
                    "report_time": report_time,
                    "details": block,
                    "destination": dest
                }
            else:
                continue

            pairing_cache[key] = result
            matched.append(result)
            continue

        expected_dest = p["destination"]
        next_expected_dest = p.get("next_destination")
        start_dt = datetime.strptime(p["start_date"], "%Y-%m-%d")
        before_report = p.get("before_report", False)
        if before_report:
            adjusted_dt = start_dt + timedelta(days=1)
        else:
            adjusted_dt = start_dt
        expected_day_code = adjusted_dt.strftime("%a").upper()[:2]
        prev_day_dt = adjusted_dt - timedelta(days=1)
        prev_expected_day_code = prev_day_dt.strftime("%a").upper()[:2]

        ignore_destination = False
        if line_dict.get("user_type") in ["cabin_crew", "pilot"]:
            duties = line_dict.get("duties", [])
            period_start_dt = datetime.strptime(line_dict["Period Start"], "%d.%b.%Y")
            pairing_start_dt = datetime.strptime(p["start_date"], "%Y-%m-%d")
            day_offset = (pairing_start_dt - period_start_dt).days
            if before_report and pairing_start_dt.day > 1:
                day_offset += 1
            base = line_dict.get("Base", "")
            if day_offset < len(duties) and day_offset + 1 < len(duties):
                current_duty = duties[day_offset]
                next_duty = duties[day_offset + 1]
                if current_duty == base and next_duty == base:
                    ignore_destination = True
                if current_duty == "-" and next_duty == base:
                    ignore_destination = True

        special_compare = False
        expected_dest_first = expected_dest_last = None
        if line_dict.get("user_type") in ["cabin_crew", "pilot"] and "<" in expected_dest:
            special_compare = True
            expected_dest_first = expected_dest[0]
            expected_dest_last = expected_dest[-1]

        matching_blocks = []
        for block in pairing_blocks:
            lines = block.splitlines()
            if lines and re.match(rf"#{number:03}\b", lines[0]):
                matching_blocks.append(block)

        found = False
        for block in matching_blocks:
            lines = block.splitlines()
            first_flight_line = None
            first_flight_dest = None
            first_flight_daycode = None

            if len(lines) >= 2:
                line = lines[1]
                flight_match = re.search(
                    r"\b([A-Z]{2})\s+(?:DH)?(\d{3,4})\s+[A-Z0-9]{2,3}\s+\d{2}\.\d{2}\s+([A-Z]{3})\s+\d{2}\.\d{2}\s+([A-Z]{3})\s+\d{2}\.\d{2}",
                    line
                )
                if flight_match:
                    first_flight_daycode = flight_match.group(1)
                    first_flight_dest = flight_match.group(4)
                    first_flight_line = line

            if ignore_destination:
                match_condition = first_flight_daycode == expected_day_code
            elif special_compare:
                if first_flight_dest and len(first_flight_dest) >= 2:
                    match_condition = (first_flight_daycode == expected_day_code and
                                       first_flight_dest[0] == expected_dest_first and
                                       first_flight_dest[-1] == expected_dest_last)
                else:
                    match_condition = False
            else:
                match_condition = first_flight_daycode == expected_day_code and first_flight_dest == expected_dest
                if not match_condition:
                    match_condition = first_flight_daycode == prev_expected_day_code and first_flight_dest == expected_dest
                if not match_condition and next_expected_dest:
                    match_condition = first_flight_daycode == expected_day_code and first_flight_dest == next_expected_dest
                if not match_condition and next_expected_dest:
                    match_condition = first_flight_daycode == prev_expected_day_code and first_flight_dest == next_expected_dest

            if match_condition:
                fd, ed = parse_pairing_times(block, p["start_date"], adjusted_for_less)
                end_date = ed.strftime("%Y-%m-%dT%H:%M") if ed else None
                report_time = None
                if lines and "REPORT AT" in lines[0]:
                    report_match = re.search(r"REPORT AT\s+(\d{2}\.\d{2})Z", lines[0])
                    if report_match:
                        report_time = report_match.group(1).replace(".", ":")

                result = {
                    "number": p["number"],
                    "start_date": p["start_date"],
                    "end_date": end_date,
                    "first_departure": fd.strftime("%Y-%m-%dT%H:%M") if fd else None,
                    "minimum_rest": None,
                    "legs": len([l for l in lines if re.search(r"\b[A-Z]{2}\s+(?:DH)?\d{3,4}", l)]),
                    "report_time": report_time,
                    "details": block,
                    "destination": p["destination"]
                }

                pairing_cache[key] = result
                matched.append(result)
                found = True
                break

        if not found:
            continue

    return matched

def build_pairing_index(pairing_blocks):
    pairing_index = {}
    for block in pairing_blocks:
        lines = block.splitlines()
        if not lines or not re.match(r"#\d{3}", lines[0]):
            continue
        number_match = re.match(r"#(\d{3})", lines[0])
        if not number_match:
            continue
        pairing_number = number_match.group(1)

        if len(lines) < 2:
            continue
        second_line = lines[1]
        flight_match = re.search(
            r"\b([A-Z]{2})\s+(?:DH)?\d{3,4}\s+[A-Z0-9]{2,3}\s+\d{2}\.\d{2}\s+[A-Z]{3}\s+\d{2}\.\d{2}\s+([A-Z]{3})",
            second_line
        )
        if not flight_match:
            continue
        day_code = flight_match.group(1)
        first_destination = flight_match.group(2)

        # استخراج أول وجهة لي أوفر
        layover_destination = get_first_layover_destination(block)

        # تخزين البلوك مرتين: مرة باستخدام أول وجهة، ومرة باستخدام أول وجهة لي أوفر
        key_first = (pairing_number, day_code, first_destination)
        pairing_index[key_first] = block
        if layover_destination:
            key_layover = (pairing_number, day_code, layover_destination)
            pairing_index[key_layover] = block

    return pairing_index


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
            temp_final_end_date = period_end + timedelta(days=10)

            for i in range(1, len(doc)):
                text = doc[i].get_text()
                if metadata["User Type"] == "cabin_crew":
                    line_pattern = r"LINE\d{4}"
                else:
                    line_pattern = r"LINE\s+\d{3}"
                if re.search(line_pattern, text):
                    line_pages.append(i)
                    blocks = re.split(rf"(?={line_pattern})", text)
                    for block in blocks:
                        if metadata["User Type"] == "cabin_crew":
                            match = re.search(r"LINE(\d{4})", block)
                        else:
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
            pairing_index = build_pairing_index(pairing_blocks) if metadata["User Type"] == "cabin_crew" else None

            for line in all_lines:
                if metadata["User Type"] == "cabin_crew":
                    matched = match_pairings(line, pairing_blocks, pairing_index, use_layover_destination=True)
                else:
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
                                layover_match = re.search(r"LAYOVER\s+(\w{3})\s+(\d+\.\d{2})", line_text)
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

            # ✅ تعديل: استخدام data["Period"] لتحديد الشهر والسنة
            period_str = metadata["Period"]  # مثل: "FEB, 2025"
            month_abbr, year = period_str.split(", ")
            month_map = {
                "JAN": "January", "FEB": "February", "MAR": "March", "APR": "April",
                "MAY": "May", "JUN": "June", "JUL": "July", "AUG": "August",
                "SEP": "September", "OCT": "October", "NOV": "November", "DEC": "December"
            }
            month_name = month_map.get(month_abbr.upper(), "Unknown")
            year = year.strip()

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