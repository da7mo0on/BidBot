document.addEventListener('DOMContentLoaded', () => {
    const uploadForm = document.getElementById('upload-form');
    const uploadSection = document.getElementById('upload-section');
    const linesSection = document.getElementById('lines-section');
    const progressBar = document.getElementById('progress-bar');
    const progress = document.getElementById('progress');
    const linesTableBody = document.getElementById('lines-table-body');
    const dutyTimelineRow = document.getElementById('duty-timeline-row');
    const dutyTimeline = document.getElementById('duty-timeline');

    const daysInPeriod = parseInt(dutyTimeline.style.minWidth) / 80;

    function resetDutyTimeline() {
        dutyTimeline.innerHTML = '';
        for (let day = 0; day <= daysInPeriod; day++) {
            const separator = document.createElement('div');
            separator.className = 'day-separator';
            separator.style.left = `${day * 80}px`;
            separator.style.height = '34px';
            dutyTimeline.appendChild(separator);
        }
    }

    resetDutyTimeline();

    // تخزين الصفوف الأصلية للترتيب الافتراضي
    let originalRows = Array.from(linesTableBody.querySelectorAll('tr'));
    let currentFilteredRows = originalRows; // لتخزين الـ Rows المفلترة الحالية
    let selectedLines = []; // لتخزين أرقام الـ Lines المختارة مع الترتيب
    let selectedLinesOrder = []; // لتخزين الترتيب النهائي بعد السحب
    let currentDuties = null; // لتخزين الدوتيز الحالية للواجهة الرئيسية
    let currentLineDuties = null; // لتخزين line.duties الحالية

    
    document.querySelector('.control-btn:first-child').addEventListener('click', () => {
        $('#filtersModal').modal('show');
    });

    // Handle file upload
    uploadForm.addEventListener('submit', (e) => {
        e.preventDefault();
        progressBar.style.display = 'block';
        let progressValue = 0;

        const interval = setInterval(() => {
            progressValue += 10;
            progress.style.width = `${progressValue}%`;
            if (progressValue >= 100) {
                clearInterval(interval);
                uploadForm.submit();
            }
        }, 300);
    });

    // Check if lines data exists (passed from Flask)
    if (linesTableBody.children.length > 0) {
        uploadSection.style.display = 'none';
        linesSection.style.display = 'block';
        attachRowListeners();
        attachSortListeners();
        adjustColumnWidths();
    }

    function attachRowListeners() {
        const rows = linesTableBody.querySelectorAll('tr');
        rows.forEach(row => {
            row.removeEventListener('click', handleRowClick);
            row.addEventListener('click', handleRowClick);
        });
    }

    function handleRowClick(e) {
        if (e.target.type !== 'checkbox') {
            const line = JSON.parse(this.dataset.line || '{}');
            const pairings = JSON.parse(this.dataset.pairings || '[]');
            toggleDetailsRow(this, pairings);
    
            document.querySelectorAll('#lines-table-body tr').forEach(row => row.classList.remove('active'));
            this.classList.add('active');
    
            resetDutyTimeline();
            currentDuties = pairings; // تحديث currentDuties
            currentLineDuties = line.duties || []; // تحديث currentLineDuties
            updateDutyTimeline(pairings, currentLineDuties);
    
            dutyTimelineRow.style.display = 'block';
        }
    }

    function showPairingDetails(pairing) {
        const modalBody = document.getElementById('pairingModalBody');
        modalBody.innerHTML = '';

        const block = document.createElement('div');
        block.classList.add('pairing-block');

        if (pairing.details === "Not Found") {
            block.textContent = `Pairing #${pairing.number}: Not Found`;
        } else {
            const dateParts = pairing.start_date.split('-');
            const formattedDate = `${dateParts[2]}-${dateParts[1]}-${dateParts[0]}`;
            const formattedTime = `${pairing.report_time}Z`;

            const lines = pairing.details.split('\n');

            let formattedDetails = `<div class="report-line">REPORT ON ${formattedDate} AT ${formattedTime}</div>`;
            lines.slice(1).forEach((line, index) => {
                if (line.includes('REPORT AT')) return;
                if (line.includes('CREDIT')) {
                    formattedDetails += `<div class="credit-line">${line}</div>`;
                    formattedDetails += `<div class="min-rest-line">Time to next flight: ${pairing.minimum_rest}</div>`;
                } else if (line.includes('LAYOVER')) {
                    const cleanedLine = line.trimStart();
                    let layoverClass = 'layover-less-24';
                    const layoverMatch = line.match(/LAYOVER\s+\w{3}\s+(\d{2}\.\d{2})/);
                    if (layoverMatch) {
                        const time = layoverMatch[1];
                        const [hours, minutes] = time.split('.').map(Number);
                        const layoverDuration = hours + minutes / 60;
                        if (layoverDuration < 24) {
                            layoverClass = 'layover-less-24';
                        } else if (layoverDuration <= 39) {
                            layoverClass = 'layover-24-39';
                        } else if (layoverDuration <= 68) {
                            layoverClass = 'layover-39-68';
                        } else {
                            layoverClass = 'layover-more-68';
                        }
                    }
                    formattedDetails += `<div class="layover-line ${layoverClass}">${cleanedLine}</div>`;
                } else if (line.trim()) {
                    const parts = line.trim().split(/\s+/);
                    const flightLine = parts.map(part => `<span class="flight-part">${part}</span>`).join('');
                    formattedDetails += `<div class="flight-line">${flightLine}</div>`;
                }
            });
            block.innerHTML = formattedDetails;
        }

        modalBody.appendChild(block);

        $('#pairingModal').modal('show');
    }

    function updateDutyTimeline(pairings, lineDuties) {
        resetDutyTimeline();
        currentDuties = pairings;
    
        const localAirports = ['JED', 'RUH', 'MED', 'NUM', 'DMM'];
        const dayMap = {};
        const occupiedDays = new Set();
    
        const periodStartDate = new Date(periodStart + "T00:00:00Z"); // تحويل periodStart إلى كائن Date
    
        pairings.forEach(pairing => {
            if (pairing.details !== "Not Found" && pairing.start_date && pairing.end_date) {
                try {
                    const startDate = new Date(pairing.start_date + "T00:00:00Z");
                    const endDate = new Date(pairing.end_date.endsWith('Z') ? pairing.end_date : pairing.end_date + "Z");
    
                    // حساب الفرق بالأيام بين start_date و period_start
                    const timeDiff = startDate - periodStartDate;
                    const dayStart = Math.floor(timeDiff / (1000 * 60 * 60 * 24)); // عدد الأيام من period_start
                    const endTimeDiff = endDate - periodStartDate;
                    const dayEnd = Math.floor(endTimeDiff / (1000 * 60 * 60 * 24));
                    const isSameDay = startDate.toISOString().split('T')[0] === endDate.toISOString().split('T')[0];
                    const effectiveDayEnd = isSameDay ? dayStart : dayEnd;
    
                    for (let day = dayStart; day <= effectiveDayEnd; day++) {
                        occupiedDays.add(day + 1); // +1 لأن الأيام في duties تبدأ من 1
                    }
    
                    if (!dayMap[dayStart]) dayMap[dayStart] = { starts: [], ends: [] };
                    if (!isSameDay && !dayMap[effectiveDayEnd]) dayMap[effectiveDayEnd] = { starts: [], ends: [] };
                    dayMap[dayStart].starts.push(pairing);
                    if (!isSameDay) dayMap[effectiveDayEnd].ends.push(pairing);
    
                    const margin = 2;
                    let leftPosition = (80 * dayStart) + margin; // الموقع نسبي لـ period_start
                    let width;
    
                    let reportHour = 0;
                    if (pairing.report_time) {
                        const reportTime = pairing.report_time;
                        const timeParts = reportTime.replace('Z', '').replace(':', '.').split('.');
                        const hours = parseInt(timeParts[0], 10);
                        const minutes = parseInt(timeParts[1] || '0', 10);
                        reportHour = hours + minutes / 60;
                    } else {
                        reportHour = startDate.getUTCHours() + startDate.getUTCMinutes() / 60;
                    }
    
                    const endHour = endDate.getUTCHours() + endDate.getUTCMinutes() / 60;
    
                    if (isSameDay) {
                        if (reportHour >= 12) {
                            leftPosition += 40;
                            width = 40 - (2 * margin);
                        } else if (endHour < 12) {
                            width = 40 - (2 * margin);
                        } else {
                            width = 80 - (2 * margin);
                        }
                    } else {
                        const fullDaysBetween = effectiveDayEnd - dayStart - 1;
                        width = (fullDaysBetween >= 0 ? fullDaysBetween * 80 : 0) + (reportHour >= 12 ? 40 : 80) + (endHour < 12 ? 40 : 80) - (2 * margin);
                        leftPosition += (reportHour >= 12 ? 40 : 0);
                    }
    
                    const duty = document.createElement('div');
                    duty.className = 'duty Flight';
                    duty.style.left = `${leftPosition}px`;
                    duty.style.minWidth = `${width}px`;
                    duty.style.width = `${width}px`;
                    duty.style.top = '4px';
                    duty.style.height = '26px';
                    duty.dataset.pairingNo = pairing.number;
                    duty.dataset.pairingDate = pairing.start_date;
                    duty.dataset.pairingLabel = pairing.number;
    
                    let displayText = pairing.number;
                    if (pairing.details) {
                        const lines = pairing.details.split('\n');
                        const layovers = [];
                        for (const line of lines) {
                            const layoverMatch = line.match(/LAYOVER\s+(\w{3})\s+(\d{2}\.\d{2})/);
                            if (layoverMatch) {
                                const city = layoverMatch[1];
                                const time = layoverMatch[2];
                                const [hours, minutes] = time.split('.').map(Number);
                                const duration = hours + minutes / 60;
                                layovers.push({ city, duration });
                            }
                        }
    
                        let firstDestination = '';
                        for (const line of lines) {
                            const flightMatch = line.match(/^[A-Z]{2}\s+(?:DH)?\d{3,4}\s+\w{3}\s+\d{2}\.\d{2}\s+\w{3}\s+\d{2}\.\d{2}\s+(\w{3})/);
                            if (flightMatch) {
                                firstDestination = flightMatch[1];
                                break;
                            }
                        }
    
                        if (layovers.length > 0) {
                            const hasInternationalLayover = layovers.some(layover => !localAirports.includes(layover.city));
                            if (hasInternationalLayover) {
                                const firstInternationalLayover = layovers.find(layover => !localAirports.includes(layover.city));
                                if (firstInternationalLayover) {
                                    displayText = firstInternationalLayover.city;
                                }
                            } else {
                                const uniqueLayoverCities = [...new Set(layovers.map(layover => layover.city))];
                                const layoverCities = uniqueLayoverCities.join(', ');
                                if (firstDestination) {
                                    displayText = `${firstDestination} (${layoverCities})`;
                                } else if (layoverCities) {
                                    displayText = layoverCities;
                                }
                            }
                        } else if (firstDestination) {
                            displayText = firstDestination;
                        }
                    }
    
                    duty.textContent = displayText;
                    duty.addEventListener('click', (event) => {
                        event.stopPropagation();
                        showPairingDetails(pairing);
                    });
    
                    dutyTimeline.appendChild(duty);
                } catch (error) {
                    console.error(`Error rendering pairing #${pairing.number}:`, error);
                }
            }
        });
    
        const otherDuties = [];
        if (Array.isArray(lineDuties)) {
            const duties = Array(daysInPeriod).fill(null);
            lineDuties.forEach((duty, index) => {
                if (index < daysInPeriod) {
                    duties[index] = duty;
                }
            });
    
            duties.forEach((duty, index) => {
                const day = index + 1;
                if (!occupiedDays.has(day)) {
                    if (duty && duty !== '-' && duty !== '<' && duty !== '') {
                        let displayText = duty;
                        if (duty === '*') {
                            displayText = 'OFF';
                        } else if (duty === 'R') {
                            displayText = 'RES';
                        } else if (/^[A-Z]{3}$/.test(duty) && duty !== 'RES') {
                            return;
                        }
                        otherDuties.push({ day, displayText });
                    }
                }
            });
        }
    
        otherDuties.forEach(duty => {
            const day = duty.day;
            const displayText = duty.displayText;
    
            const margin = 2;
            const leftPosition = (80 * (day - 1)) + margin;
            const width = 80 - (2 * margin);
    
            const dutyElement = document.createElement('div');
            dutyElement.className = `duty ${displayText === 'OFF' ? 'DaysOff' : displayText === 'RES' ? 'StandBy' : 'Unknown'}`;
            dutyElement.style.left = `${leftPosition}px`;
            dutyElement.style.minWidth = `${width}px`;
            dutyElement.style.width = `${width}px`;
            dutyElement.style.top = '4px';
            dutyElement.style.height = '26px';
            dutyElement.textContent = displayText;
    
            dutyTimeline.appendChild(dutyElement);
        });
    }

    function attachSortListeners() {
        const headers = document.querySelectorAll('#lines-table th[data-sort]');
        headers.forEach(header => {
            header.removeEventListener('click', handleSortClick);
            header.addEventListener('click', handleSortClick);
        });
    }

    function handleSortClick() {
        const sortKey = this.dataset.sort;
        let currentOrder = this.dataset.order || 'default';
        let newOrder;
    
        if (currentOrder === 'default') {
            newOrder = 'asc';
            this.textContent = this.textContent.replace('↕', '↑');
        } else if (currentOrder === 'asc') {
            newOrder = 'desc';
            this.textContent = this.textContent.replace('↑', '↓');
        } else if (currentOrder === 'desc') {
            newOrder = 'default';
            this.textContent = this.textContent.replace('↓', '↕');
        }
        this.dataset.order = newOrder;
    
        const activeRow = document.querySelector('#lines-table-body tr.active');
        let activeLineNumber = null;
        let activePairings = null;
        let activeLine = null;
        if (activeRow) {
            activeLineNumber = activeRow.cells[1].textContent.trim();
            activePairings = JSON.parse(activeRow.dataset.pairings || '[]');
            activeLine = JSON.parse(activeRow.dataset.line || '{}');
        }
    
        let rowsArray = Array.from(linesTableBody.querySelectorAll('tr'));
        let pairingsData = rowsArray.map(row => row.dataset.pairings);
    
        let sortedRows;
        let sortedPairingsData;
        if (newOrder === 'default') {
            sortedRows = currentFilteredRows; // استخدام الـ Rows المفلترة الحالية
            sortedPairingsData = currentFilteredRows.map(row => row.dataset.pairings);
        } else {
            let rowsWithPairings = rowsArray.map((row, index) => ({
                row: row,
                pairingData: pairingsData[index]
            }));
    
            let rowsWithValues = [];
            let rowsWithoutValues = [];
            rowsWithPairings.forEach(item => {
                let val = item.row.cells[getColumnIndex(sortKey)].textContent.trim();
                if (sortKey === 'minimum_rest') {
                    val = parseTime(val);
                    if (val === null) {
                        rowsWithoutValues.push(item);
                    } else {
                        rowsWithValues.push({ ...item, sortValue: val });
                    }
                } else {
                    if (['block_hours', 'carry_over'].includes(sortKey)) {
                        val = parseTime(val);
                    } else {
                        val = isNaN(val) ? val : parseFloat(val);
                    }
                    rowsWithValues.push({ ...item, sortValue: val });
                }
            });
    
            rowsWithValues.sort((a, b) => {
                let valA = a.sortValue;
                let valB = b.sortValue;
    
                if (newOrder === 'asc') {
                    return valA > valB ? 1 : -1;
                } else {
                    return valA < valB ? 1 : -1;
                }
            });
    
            sortedRows = [...rowsWithValues.map(item => item.row), ...rowsWithoutValues.map(item => item.row)];
            sortedPairingsData = [...rowsWithValues.map(item => item.pairingData), ...rowsWithoutValues.map(item => item.pairingData)];
        }
    
        linesTableBody.innerHTML = '';
        sortedRows.forEach((row, index) => {
            row.dataset.pairings = sortedPairingsData[index];
            linesTableBody.appendChild(row);
        });
    
        attachRowListeners();
    
        if (activeLineNumber && activePairings) {
            const newActiveRow = Array.from(linesTableBody.querySelectorAll('tr')).find(row => 
                row.cells[1].textContent.trim() === activeLineNumber
            );
            if (newActiveRow) {
                newActiveRow.classList.add('active');
                currentDuties = activePairings;
                currentLineDuties = activeLine ? activeLine.duties || [] : [];
                updateDutyTimeline(activePairings, currentLineDuties);
            } else {
                resetDutyTimeline();
                currentDuties = null;
                currentLineDuties = null;
            }
        } else {
            resetDutyTimeline();
            currentDuties = null;
            currentLineDuties = null;
        }
    }

    function getColumnIndex(sortKey) {
        const headers = Array.from(document.querySelectorAll('#lines-table th'));
        return headers.findIndex(header => header.dataset.sort === sortKey);
    }

    function toggleDetailsRow(row, pairings) {
        const existingDetails = row.nextElementSibling?.classList.contains('details-row');
        if (existingDetails) {
            // إذا كان الصف التالي هو صف التفاصيل (أي أن اللاين لديه تفاصيل مفتوحة)، أغلق جميع صفوف التفاصيل
            document.querySelectorAll('.details-row').forEach(detailsRow => detailsRow.remove());
            return;
        }
    
        // إغلاق جميع صفوف التفاصيل المفتوحة في الجدول قبل فتح صف جديد
        document.querySelectorAll('.details-row').forEach(detailsRow => detailsRow.remove());
    
        const detailsRow = document.createElement('tr');
        detailsRow.classList.add('details-row');
        const detailsCell = document.createElement('td');
        detailsCell.colSpan = 12;
        const pairingGrid = document.createElement('div');
        pairingGrid.classList.add('pairing-grid');
    
        pairings.forEach(pairing => {
            const block = document.createElement('div');
            block.classList.add('pairing-block');
            if (pairing.details === "Not Found") {
                block.textContent = `Pairing #${pairing.number}: Not Found`;
                pairingGrid.appendChild(block);
                return;
            }
    
            const dateParts = pairing.start_date.split('-');
            const formattedDate = `${dateParts[2]}-${dateParts[1]}-${dateParts[0]}`;
            const formattedTime = `${pairing.report_time}Z`;
    
            const lines = pairing.details.split('\n');
    
            let formattedDetails = `<div class="report-line">REPORT ON ${formattedDate} AT ${formattedTime}</div>`;
            lines.slice(1).forEach((line, index) => {
                if (line.includes('REPORT AT')) return;
                if (line.includes('CREDIT')) {
                    formattedDetails += `<div class="credit-line">${line}</div>`;
                    formattedDetails += `<div class="min-rest-line">Time to next flight: ${pairing.minimum_rest}</div>`;
                } else if (line.includes('LAYOVER')) {
                    const cleanedLine = line.trimStart();
                    let layoverClass = 'layover-less-24';
                    const layoverMatch = line.match(/LAYOVER\s+\w{3}\s+(\d{2}\.\d{2})/);
                    if (layoverMatch) {
                        const time = layoverMatch[1];
                        const [hours, minutes] = time.split('.').map(Number);
                        const layoverDuration = hours + minutes / 60;
                        if (layoverDuration < 24) {
                            layoverClass = 'layover-less-24';
                        } else if (layoverDuration <= 39) {
                            layoverClass = 'layover-24-39';
                        } else if (layoverDuration <= 68) {
                            layoverClass = 'layover-39-68';
                        } else {
                            layoverClass = 'layover-more-68';
                        }
                    }
                    formattedDetails += `<div class="layover-line ${layoverClass}">${cleanedLine}</div>`;
                } else if (line.trim()) {
                    const parts = line.trim().split(/\s+/);
                    const flightLine = parts.map(part => `<span class="flight-part">${part}</span>`).join('');
                    formattedDetails += `<div class="flight-line">${flightLine}</div>`;
                }
            });
            block.innerHTML = formattedDetails;
            pairingGrid.appendChild(block);
        });
    
        detailsCell.appendChild(pairingGrid);
        detailsRow.appendChild(detailsCell);
        row.insertAdjacentElement('afterend', detailsRow);
    }

    function adjustColumnWidths() {
        const table = document.getElementById('lines-table');
        const headers = table.querySelectorAll('th');
        const rows = table.querySelectorAll('tbody tr');

        headers.forEach((header, index) => {
            if (index === headers.length - 1) return;
            let maxWidth = header.offsetWidth;
            rows.forEach(row => {
                const cell = row.children[index];
                const width = cell.offsetWidth;
                if (width > maxWidth) maxWidth = width;
            });
            header.style.width = `${maxWidth + 10}px`;
        });

        headers[headers.length - 1].style.width = 'auto';
    }

    function parseTime(time) {
        if (!time || time === '—' || time.includes('More than')) return null;
        const [hours, minutes] = time.split(':').map(Number);
        return hours * 60 + minutes;
    }

    function formatTime(minutes) {
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}Z`;
    }

    function formatDecimalHours(decimal) {
        const hours = Math.floor(decimal);
        const minutes = Math.round((decimal - hours) * 60);
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
    }

    function populateFilterOptions() {
        if (typeof $.fn.multiselect === 'undefined') {
            console.error("Bootstrap Multiselect is not loaded!");
            return;
        }
    
        const lines = Array.from(linesTableBody.querySelectorAll('tr')).map(row => JSON.parse(row.dataset.line || '{}'));
        const pairingsData = Array.from(linesTableBody.querySelectorAll('tr')).map(row => JSON.parse(row.dataset.pairings || '[]'));
        
        if (!lines.length) {
            console.error("No lines data found in linesTableBody.");
            return;
        }
    
        // 1. Line Types (ترتيب أبجدي)
        const lineTypes = [...new Set(lines.map(line => line.type).filter(type => type && type !== '-'))].sort();
        const lineTypesSelect = $('#line-types');
        lineTypesSelect.empty();
        lineTypes.forEach(type => {
            lineTypesSelect.append(`<option value="${type}">${type}</option>`);
        });
        lineTypesSelect.multiselect({
            enableFiltering: true,
            includeSelectAllOption: true,
            buttonWidth: '100%',
            maxHeight: 300,
            nonSelectedText: 'Choose Line(s) Type(s)',
            buttonText: function(options, select) {
                if (options.length === 0) {
                    return 'Choose Line(s) Type(s)';
                } else if (options.length === select.children('option').length) {
                    return 'All selected';
                } else {
                    var selected = [];
                    options.each(function() {
                        selected.push($(this).text());
                    });
                    return selected.join(', ');
                }
            },
            templates: {
                button: '<button type="button" class="multiselect dropdown-toggle" data-toggle="dropdown"><span class="multiselect-selected-text"></span> <b class="caret"></b><span class="clear-btn" style="float: right; margin-left: 5px; cursor: pointer;">×</span></button>'
            },
            onInitialized: function(select, container) {
                $(container).find('.clear-btn').on('click', function(e) {
                    e.stopPropagation();
                    lineTypesSelect.multiselect('deselectAll', false);
                    lineTypesSelect.multiselect('refresh');
                });
            }
        });

    
        // 2. Desired Layovers (ترتيب أبجدي)
        const allLayovers = new Set();
        pairingsData.flat().forEach(pairing => {
            if (pairing.details && pairing.details !== "Not Found") {
                pairing.details.split('\n').forEach(line => {
                    const layoverMatch = line.match(/LAYOVER\s+(\w{3})\s+\d{2}\.\d{2}/);
                    if (layoverMatch) allLayovers.add(layoverMatch[1]);
                });
            }
        });
        const sortedLayovers = [...allLayovers].sort();
        const layoversSelect = $('#desired-layovers');
        layoversSelect.empty();
        sortedLayovers.forEach(city => {
            layoversSelect.append(`<option value="${city}">${city}</option>`);
        });
        layoversSelect.multiselect({
            enableFiltering: true,
            includeSelectAllOption: true,
            buttonWidth: '100%',
            maxHeight: 300,
            nonSelectedText: 'Choose Desired Layover(s)',
            buttonText: function(options, select) {
                if (options.length === 0) {
                    return 'Choose Desired Layover(s)';
                } else if (options.length === select.children('option').length) {
                    return 'All selected';
                } else {
                    var selected = [];
                    options.each(function() {
                        selected.push($(this).text());
                    });
                    return selected.join(', ');
                }
            },
            templates: {
                button: '<button type="button" class="multiselect dropdown-toggle" data-toggle="dropdown"><span class="multiselect-selected-text"></span> <b class="caret"></b><span class="clear-btn" style="float: right; margin-left: 5px; cursor: pointer;">×</span></button>'
            },
            onInitialized: function(select, container) {
                $(container).find('.clear-btn').on('click', function(e) {
                    e.stopPropagation();
                    layoversSelect.multiselect('deselectAll', false);
                    layoversSelect.multiselect('refresh');
                });
            }
        });

    
        // 3. Layover Length
        const layoverLengthSelect = $('#layover-length');
        layoverLengthSelect.multiselect({
            enableFiltering: true,
            includeSelectAllOption: true,
            buttonWidth: '100%',
            maxHeight: 300,
            nonSelectedText: 'Choose Desired Layover Length',
            buttonText: function(options, select) {
                if (options.length === 0) {
                    return 'Choose Desired Layover Length';
                } else if (options.length === select.children('option').length) {
                    return 'All selected';
                } else {
                    var selected = [];
                    options.each(function() {
                        selected.push($(this).text());
                    });
                    return selected.join(', ');
                }
            },
            templates: {
                button: '<button type="button" class="multiselect dropdown-toggle" data-toggle="dropdown"><span class="multiselect-selected-text"></span> <b class="caret"></b><span class="clear-btn" style="float: right; margin-left: 5px; cursor: pointer;">×</span></button>'
            },
            onInitialized: function(select, container) {
                $(container).find('.clear-btn').on('click', function(e) {
                    e.stopPropagation();
                    layoverLengthSelect.multiselect('deselectAll', false);
                    layoverLengthSelect.multiselect('refresh');
                });
            }
        });

    
        // 4. Excluded Destinations (ترتيب أبجدي)
        const allDestinations = new Set(lines.flatMap(line => line.destinations || []));
        const sortedDestinations = [...allDestinations].sort();
        const destinationsSelect = $('#excluded-destinations');
        destinationsSelect.empty();
        sortedDestinations.forEach(dest => {
            destinationsSelect.append(`<option value="${dest}">${dest}</option>`);
        });
        destinationsSelect.multiselect({
            enableFiltering: true,
            includeSelectAllOption: true,
            buttonWidth: '100%',
            maxHeight: 300,
            nonSelectedText: 'Choose Excluded Destination(s)',
            buttonText: function(options, select) {
                if (options.length === 0) {
                    return 'Choose Excluded Destination(s)';
                } else if (options.length === select.children('option').length) {
                    return 'All selected';
                } else {
                    var selected = [];
                    options.each(function() {
                        selected.push($(this).text());
                    });
                    return selected.join(', ');
                }
            },
            templates: {
                button: '<button type="button" class="multiselect dropdown-toggle" data-toggle="dropdown"><span class="multiselect-selected-text"></span> <b class="caret"></b><span class="clear-btn" style="float: right; margin-left: 5px; cursor: pointer;">×</span></button>'
            },
            onInitialized: function(select, container) {
                $(container).find('.clear-btn').on('click', function(e) {
                    e.stopPropagation();
                    destinationsSelect.multiselect('deselectAll', false);
                    destinationsSelect.multiselect('refresh');
                });
            }
        });
    
        // 5. Desired Days Off
        const daysOffSelect = $('#desired-days-off');
        daysOffSelect.empty();
        const dateElements = document.querySelectorAll('.duty-timeline-header .day span');
        const dateList = Array.from(dateElements).map((span, index) => {
            const dayNum = span.firstChild.textContent.trim().padStart(2, '0');
            const weekday = span.querySelector('small:last-child')?.textContent.trim().toUpperCase() || '---';
            return `${dayNum}-${weekday}`;
        });
        dateList.forEach((date, index) => {
            daysOffSelect.append(`<option value="${index + 1}">${date}</option>`);
        });
        daysOffSelect.multiselect({
            enableFiltering: true,
            includeSelectAllOption: true,
            buttonWidth: '100%',
            maxHeight: 300,
            nonSelectedText: 'Choose Desired Day(s) Off',
            buttonText: function(options, select) {
                if (options.length === 0) {
                    return 'Choose Desired Day(s) Off';
                } else if (options.length === select.children('option').length) {
                    return 'All selected';
                } else {
                    var selected = [];
                    options.each(function() {
                        selected.push($(this).text());
                    });
                    return selected.join(', ');
                }
            },
            templates: {
                button: '<button type="button" class="multiselect dropdown-toggle" data-toggle="dropdown"><span class="multiselect-selected-text"></span> <b class="caret"></b><span class="clear-btn" style="float: right; margin-left: 5px; cursor: pointer;">×</span></button>'
            },
            onInitialized: function(select, container) {
                $(container).find('.clear-btn').on('click', function(e) {
                    e.stopPropagation();
                    daysOffSelect.multiselect('deselectAll', false);
                    daysOffSelect.multiselect('refresh');
                });
            }
        });
    
        // الكود الخاص بالـ Sliders (بدون تغيير)
        const sliders = [
            { id: 'block-hours-slider', data: lines.map(line => parseTime(line.block_hours) / 60 || 0), label: 'block-hours-range', unit: '', format: formatDecimalHours },
            { id: 'days-off-slider', data: lines.map(line => line.off_days || 0), label: 'days-off-range', unit: ' Days' },
            { id: 'report-time-slider', data: pairingsData.flat().map(p => p.report_time ? parseTime(p.report_time) : null).filter(Boolean), label: 'report-time-range', unit: '', format: formatTime },
            { id: 'four-legs-slider', data: lines.map(line => line.four_legs_count || 0), label: 'four-legs-range', unit: '' },
            { id: 'pairings-slider', data: lines.map(line => line.pairings_count || 0), label: 'pairings-range', unit: '' },
            { id: 'total-legs-slider', data: lines.map(line => line.total_legs || 0), label: 'total-legs-range', unit: '' },
            { id: 'min-rest-slider', data: lines.map(line => line.minimum_rest && line.minimum_rest !== '—' && !line.minimum_rest.includes('More') ? parseTime(line.minimum_rest) / 60 : 0).filter(v => v > 0), label: 'min-rest-range', unit: '', format: formatDecimalHours, single: true }
        ];
    
        sliders.forEach(slider => {
            const element = document.getElementById(slider.id);
            if (element.noUiSlider) element.noUiSlider.destroy();
            const values = slider.data.length ? [Math.min(...slider.data), Math.max(...slider.data)] : [0, slider.id === 'report-time-slider' ? 1439 : 100];
            noUiSlider.create(element, {
                start: slider.single ? values[0] : [values[0], values[1]],
                connect: slider.single ? false : true,
                range: { 'min': values[0], 'max': values[1] },
                step: 1
            });
            element.noUiSlider.on('update', () => {
                const value = element.noUiSlider.get();
                if (slider.single) {
                    document.getElementById(slider.label).textContent = slider.format ? `${slider.format(value)}${slider.unit}` : `${value}${slider.unit}`;
                    if (slider.id === 'min-rest-slider') {
                        const percentage = ((value - values[0]) / (values[1] - values[0])) * 100;
                        element.style.setProperty('--connect-end', `${percentage}%`);
                    }
                } else {
                    const [min, max] = value.map(Number);
                    document.getElementById(slider.label).textContent = slider.format ? `${slider.format(min)} - ${slider.format(max)}${slider.unit}` : `${min} - ${max}${slider.unit}`;
                }
            });
        });
    }

    document.getElementById('apply-filters').addEventListener('click', () => {
        const lines = Array.from(originalRows).map(row => ({
            row,
            data: JSON.parse(row.dataset.line || '{}'),
            pairings: JSON.parse(row.dataset.pairings || '[]')
        }));
    
        const selectedLineTypes = $('#line-types').val() || [];
        const hideCarryover = document.getElementById('hide-carryover').checked;
        const hideDeadhead = document.getElementById('hide-deadhead').checked;
        const weekendsOff = document.getElementById('weekends-off').checked;
        const desiredLayovers = $('#desired-layovers').val() || [];
        const layoverLengths = $('#layover-length').val() || [];
        const excludedDestinations = $('#excluded-destinations').val() || [];
        const [blockHoursMin, blockHoursMax] = document.getElementById('block-hours-slider').noUiSlider.get().map(Number);
        const [daysOffMin, daysOffMax] = document.getElementById('days-off-slider').noUiSlider.get().map(Number);
        const desiredDaysOff = $('#desired-days-off').val().map(Number) || [];
        const [reportTimeMin, reportTimeMax] = document.getElementById('report-time-slider').noUiSlider.get().map(Number);
        const [fourLegsMin, fourLegsMax] = document.getElementById('four-legs-slider').noUiSlider.get().map(Number);
        const [pairingsMin, pairingsMax] = document.getElementById('pairings-slider').noUiSlider.get().map(Number);
        const [totalLegsMin, totalLegsMax] = document.getElementById('total-legs-slider').noUiSlider.get().map(Number);
        const minRestMin = document.getElementById('min-rest-slider').noUiSlider.get();
    
        const filteredLines = lines.filter(line => {
            const { data, pairings } = line;
    
            if (selectedLineTypes.length > 0 && !selectedLineTypes.includes(data.type)) return false;
            if (hideCarryover && data.carry_over > 0) return false;
            if (hideDeadhead && data.deadheads > 0) return false;
            if (weekendsOff) {
                const duties = data.duties || [];
                const daysHeader = Array.from(document.querySelectorAll('.duty-timeline-header .day span'));
                const startDate = new Date('2025-04-01');
                const fridaysSaturdays = daysHeader
                    .map((span, index) => {
                        const date = new Date(startDate);
                        date.setDate(date.getDate() + index);
                        const weekday = date.toLocaleString('en-US', { weekday: 'short' });
                        return { index: index + 1, weekday };
                    })
                    .filter(day => day.weekday === 'Fri' || day.weekday === 'Sat')
                    .map(day => day.index)
                    .filter(index => index <= duties.length);
                if (fridaysSaturdays.length === 0 || !fridaysSaturdays.every(day => duties[day - 1] === '*')) return false;
            }
    
            const layoverCities = pairings.flatMap(p => 
                p.details && p.details !== "Not Found" ? 
                p.details.split('\n').filter(l => l.includes('LAYOVER')).map(l => l.match(/LAYOVER\s+(\w{3})/)?.[1]) : []
            ).filter(Boolean);
            const layoverDurations = pairings.flatMap(p => 
                p.details && p.details !== "Not Found" ? 
                p.details.split('\n').filter(l => l.includes('LAYOVER')).map(l => {
                    const match = l.match(/LAYOVER\s+\w{3}\s+(\d{2}\.\d{2})/);
                    if (match) {
                        const [hours, minutes] = match[1].split('.').map(Number);
                        return hours + minutes / 60;
                    }
                    return null;
                }) : []
            ).filter(Boolean);
    
            if (desiredLayovers.length > 0 && !desiredLayovers.some(city => layoverCities.includes(city))) return false;
            if (layoverLengths.length > 0) {
                if (layoverLengths.includes('no-layovers') && layoverDurations.length > 0) return false;
                if (!layoverLengths.includes('no-layovers') && layoverDurations.length > 0) {
                    if (!layoverDurations.every(duration => {
                        return (
                            (layoverLengths.includes('less-24') && duration < 24) ||
                            (layoverLengths.includes('24-39') && duration >= 24 && duration <= 39) ||
                            (layoverLengths.includes('39-68') && duration > 39 && duration <= 68) ||
                            (layoverLengths.includes('more-68') && duration > 68)
                        );
                    })) return false;
                }
            }
    
            const arrivalDestinations = data.destinations || [];
            if (excludedDestinations.length > 0 && arrivalDestinations.some(dest => excludedDestinations.includes(dest))) return false;
    
            const blockHours = parseTime(data.block_hours) / 60 || 0;
            if (blockHours < blockHoursMin || blockHours > blockHoursMax) return false;
            const daysOff = data.off_days || 0;
            if (daysOff < daysOffMin || daysOff > daysOffMax) return false;
            if (desiredDaysOff.length > 0) {
                const duties = data.duties || [];
                if (!desiredDaysOff.every(day => duties[day - 1] === '*')) return false;
            }
            if (pairings.length > 0) {
                const reportTimes = pairings.map(p => p.report_time ? parseTime(p.report_time) : null).filter(Boolean);
                if (reportTimes.length > 0 && !reportTimes.every(time => time >= reportTimeMin && time <= reportTimeMax)) return false;
            }
    
            const fourLegs = data.four_legs_count || 0;
            if (fourLegs < fourLegsMin || fourLegs > fourLegsMax) return false;
            const pairingsCount = data.pairings_count || 0;
            if (pairingsCount < pairingsMin || pairingsCount > pairingsMax) return false;
            const totalLegs = data.total_legs || 0;
            if (totalLegs < totalLegsMin || totalLegs > totalLegsMax) return false;
            const minRest = data.minimum_rest && data.minimum_rest !== '—' && !data.minimum_rest.includes('More') ? 
                parseTime(data.minimum_rest) / 60 : Infinity;
            if (minRest < minRestMin) return false;
    
            return true;
        });
    
        linesTableBody.innerHTML = '';
        filteredLines.forEach(line => linesTableBody.appendChild(line.row));
        currentFilteredRows = filteredLines.map(line => line.row); // تحديث الـ Rows المفلترة
        attachRowListeners();
    
        Array.from(linesTableBody.querySelectorAll('tr')).forEach(row => {
            const lineNumber = row.cells[1].textContent.trim();
            row.querySelector('.select-line').checked = selectedLines.includes(lineNumber);
        });
        updateBidSheetButton();
    
        if (filteredLines.length > 0 && currentDuties) {
            updateDutyTimeline(currentDuties, currentLineDuties);
        } else {
            resetDutyTimeline();
            currentDuties = null;
            currentLineDuties = null;
        }
    
        $('#filtersModal').modal('hide');
    });

    document.getElementById('reset-filters').addEventListener('click', () => {
        $('#line-types').multiselect('deselectAll', false).multiselect('refresh');
        document.getElementById('hide-carryover').checked = false;
        document.getElementById('hide-deadhead').checked = false;
        document.getElementById('weekends-off').checked = false;
        $('#desired-layovers').multiselect('deselectAll', false).multiselect('refresh');
        $('#layover-length').multiselect('deselectAll', false).multiselect('refresh');
        $('#excluded-destinations').multiselect('deselectAll', false).multiselect('refresh');
        document.getElementById('block-hours-slider').noUiSlider.reset();
        document.getElementById('days-off-slider').noUiSlider.reset();
        $('#desired-days-off').multiselect('deselectAll', false).multiselect('refresh');
        document.getElementById('report-time-slider').noUiSlider.reset();
        document.getElementById('four-legs-slider').noUiSlider.reset();
        document.getElementById('pairings-slider').noUiSlider.reset();
        document.getElementById('total-legs-slider').noUiSlider.reset();
        document.getElementById('min-rest-slider').noUiSlider.reset();

        linesTableBody.innerHTML = '';
        originalRows.forEach(row => linesTableBody.appendChild(row));
        attachRowListeners();
    });

    if (linesTableBody.children.length > 0) {
        populateFilterOptions();
    }

    // تحديث عدد الـ Checkboxes في زر Bid Sheet
    function updateBidSheetButton() {
        const selectedCount = selectedLines.length; // استخدام عدد اللاينات في selectedLines
        document.getElementById('bid-sheet-btn').textContent = `Bid Sheet (${selectedCount})`;
    }

    // ربط حدث التغيير لكل Checkbox
    function attachCheckboxListeners() {
        const checkboxes = linesTableBody.querySelectorAll('.select-line');
        checkboxes.forEach(checkbox => {
            checkbox.removeEventListener('change', handleCheckboxChange);
            checkbox.addEventListener('change', handleCheckboxChange);
        });
    }

    function handleCheckboxChange() {
        const row = this.closest('tr');
        const lineNumber = row.cells[1].textContent.trim();
        if (this.checked) {
            if (!selectedLines.includes(lineNumber)) {
                selectedLines.push(lineNumber); // إضافة اللاين إلى المصفوفة بناءً على ترتيب الاختيار
            }
        } else {
            selectedLines = selectedLines.filter(num => num !== lineNumber); // إزالة اللاين من المصفوفة
        }
        updateBidSheetButton();
    }

    // استدعاء المستمع عند التحميل
    attachCheckboxListeners();

    // إعادة ربط المستمعات بعد أي تغيير في الجدول
    const originalAttachRowListeners = attachRowListeners;
    attachRowListeners = function() {
        originalAttachRowListeners();
        attachCheckboxListeners();
    };

    // فتح نافذة Bid Sheet كـ Modal
    document.getElementById('bid-sheet-btn').addEventListener('click', () => {
        $('.modal').modal('hide');
        const existingDetails = document.querySelector('.details-row');
        if (existingDetails) {
            existingDetails.remove();
        }
    
        resetDutyTimeline(); // إفراغ جدول الأيام في الواجهة الرئيسية عند فتح Bid Sheet
    
        // استخدام الصفوف الأصلية للحصول على اللاينات المختارة
        const selectedRowsMap = new Map();
        originalRows.forEach(row => {
            const lineNumber = row.cells[1].textContent.trim();
            if (selectedLines.includes(lineNumber)) {
                selectedRowsMap.set(lineNumber, {
                    line: JSON.parse(row.dataset.line || '{}'),
                    pairings: JSON.parse(row.dataset.pairings || '[]')
                });
            }
        });
    
        // ترتيب اللاينات بناءً على ترتيب الاختيار أو الترتيب المحفوظ
        const orderedLineNumbers = selectedLinesOrder.length > 0 ? selectedLinesOrder : selectedLines;
        const selectedRows = orderedLineNumbers
            .map(lineNumber => selectedRowsMap.get(lineNumber))
            .filter(row => row !== undefined);
    
        // إضافة أي لاينات جديدة تم تحديدها
        const newLineNumbers = selectedLines.filter(num => !orderedLineNumbers.includes(num));
        newLineNumbers.forEach(lineNumber => {
            const rowData = selectedRowsMap.get(lineNumber);
            if (rowData) {
                selectedRows.push(rowData);
            }
        });
    
        if (selectedRows.length === 0) {
            alert('Please select at least one line to generate the Bid Sheet.');
            return;
        }
    
        const bidLinesTableBody = document.getElementById('bid-lines-table-body');
        bidLinesTableBody.innerHTML = '';
        selectedRows.forEach((item, index) => {
            const row = document.createElement('tr');
            row.dataset.line = JSON.stringify(item.line);
            row.dataset.pairings = JSON.stringify(item.pairings);
            row.draggable = true;
            row.innerHTML = `
                <td><input type="checkbox" class="select-line" checked></td>
                <td>${item.line.line_number}</td>
                <td>${item.line.type || '-'}</td>
                <td>${item.line.block_hours || '00:00'}</td>
                <td>${item.line.off_days || 0}</td>
                <td>${item.line.total_legs}</td>
                <td>${item.line.four_legs_count}</td>
                <td>${item.line.minimum_rest || '—'}</td>
                <td>${item.line.pairings_count}</td>
                <td>${formatCarryOver(item.line.carry_over)}</td>
                <td>${item.line.deadheads}</td>
                <td>${formatLayovers(item.line.layovers)}</td>
            `;
            bidLinesTableBody.appendChild(row);
        });
    
        setupBidDutyTimeline();
        attachBidRowListeners();
        attachBidCheckboxListeners();
        attachBidDragListeners();
        updateCopyLines();
    
        $('#bidSheetModal').modal('show');
    
        // إزالة جميع الـ backdrops عند إغلاق bidSheetModal
        $('#bidSheetModal').on('hidden.bs.modal', function () {
            const backdrops = document.querySelectorAll('.modal-backdrop');
            backdrops.forEach(backdrop => backdrop.remove());
            document.body.classList.remove('modal-open');
    
            resetDutyTimeline();
    
            // استعادة الدوتيز بناءً على currentDuties و currentLineDuties
            setTimeout(() => {
                if (currentDuties) {
                    updateDutyTimeline(currentDuties, currentLineDuties);
                }
            }, 100); // تأخير بسيط لضمان اكتمال إغلاق النافذة
        });
    });

    // إعداد جدول الأيام في Bid Sheet
    function setupBidDutyTimeline() {
        const bidDutyTimelineHeader = document.getElementById('bid-duty-timeline-header');
        const bidDutyTimeline = document.getElementById('bid-duty-timeline');
        const bidDutyTimelineRow = document.getElementById('bid-duty-timeline-row');
        const daysInPeriod = parseInt(document.getElementById('duty-timeline').style.minWidth) / 80;

        bidDutyTimelineHeader.innerHTML = '';
        bidDutyTimeline.innerHTML = '';
        bidDutyTimeline.style.minWidth = `${daysInPeriod * 80}px`;
        bidDutyTimelineRow.style.minWidth = `${daysInPeriod * 80}px`;
        bidDutyTimelineHeader.style.minWidth = `${daysInPeriod * 80}px`;

        const dateElements = document.querySelectorAll('.duty-timeline-header .day');
        dateElements.forEach((day, i) => {
            const clonedDay = day.cloneNode(true);
            clonedDay.style.left = `${i * 80}px`;
            bidDutyTimelineHeader.appendChild(clonedDay);

            const separator = document.createElement('div');
            separator.className = 'day-separator';
            separator.style.left = `${i * 80}px`;
            separator.style.height = '34px';
            bidDutyTimeline.appendChild(separator);
        });
    }

    // مستمعات الأحداث لـ Bid Sheet
    function attachBidRowListeners() {
        const rows = document.getElementById('bid-lines-table-body').querySelectorAll('tr');
        rows.forEach(row => {
            row.removeEventListener('click', handleBidRowClick);
            row.addEventListener('click', handleBidRowClick);
        });
    }

    function handleBidRowClick(e) {
        if (e.target.type !== 'checkbox') {
            const line = JSON.parse(this.dataset.line || '{}');
            const pairings = JSON.parse(this.dataset.pairings || '[]');
            toggleDetailsRow(this, pairings);
            document.querySelectorAll('#bid-lines-table-body tr').forEach(row => row.classList.remove('active'));
            this.classList.add('active');
            updateBidDutyTimeline(pairings, line.duties || []);
        }
    }

    function attachBidCheckboxListeners() {
        const checkboxes = document.getElementById('bid-lines-table-body').querySelectorAll('.select-line');
        checkboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                const row = checkbox.closest('tr');
                const lineNumber = row.cells[1].textContent.trim();
                if (!checkbox.checked) {
                    row.remove();
                    selectedLines = selectedLines.filter(num => num !== lineNumber); // إزالة اللاين من القائمة المختارة
                    selectedLinesOrder = selectedLinesOrder.filter(num => num !== lineNumber); // تحديث الترتيب المحفوظ
                    const mainRow = Array.from(document.getElementById('lines-table-body').querySelectorAll('tr'))
                        .find(r => r.cells[1].textContent.trim() === lineNumber);
                    if (mainRow) {
                        mainRow.querySelector('.select-line').checked = false;
                    }
                }
                updateCopyLines();
                updateBidSheetButton();
            });
        });
    }

    function attachBidDragListeners() {
        const bidLinesTableBody = document.getElementById('bid-lines-table-body');
        let draggedRow = null;
        let placeholder = null;
        let lastTargetRow = null;
        let touchStartX = 0;
        let touchStartY = 0;
    
        // دعم أجهزة الماوس (Drag and Drop)
        bidLinesTableBody.addEventListener('dragstart', (e) => {
            draggedRow = e.target.closest('tr');
            e.dataTransfer.effectAllowed = 'move';
            placeholder = document.createElement('tr');
            placeholder.className = 'drag-placeholder';
            placeholder.innerHTML = '<td colspan="12"></td>';
        });
    
        bidLinesTableBody.addEventListener('dragover', (e) => {
            e.preventDefault();
            const targetRow = e.target.closest('tr');
            if (targetRow && targetRow !== draggedRow && !targetRow.classList.contains('details-row')) {
                if (lastTargetRow !== targetRow) {
                    lastTargetRow = targetRow;
                    if (placeholder && placeholder.parentNode) {
                        placeholder.parentNode.removeChild(placeholder);
                    }
                    const rect = targetRow.getBoundingClientRect();
                    const midY = rect.top + (rect.height / 2);
                    if (e.clientY < midY) {
                        targetRow.parentNode.insertBefore(placeholder, targetRow);
                    } else {
                        targetRow.parentNode.insertBefore(placeholder, targetRow.nextSibling);
                    }
                    setTimeout(() => {
                        placeholder.classList.add('visible');
                    }, 10);
                }
            }
        });
    
        bidLinesTableBody.addEventListener('dragleave', (e) => {
            if (placeholder && placeholder.parentNode) {
                placeholder.parentNode.removeChild(placeholder);
            }
            lastTargetRow = null;
        });
    
        bidLinesTableBody.addEventListener('dragend', (e) => {
            if (placeholder && placeholder.parentNode) {
                placeholder.parentNode.removeChild(placeholder);
            }
            placeholder = null;
            lastTargetRow = null;
        });
    
        bidLinesTableBody.addEventListener('drop', (e) => {
            e.preventDefault();
            const targetRow = e.target.closest('tr');
            if (targetRow && draggedRow !== targetRow && !targetRow.classList.contains('details-row')) {
                document.querySelectorAll('.details-row').forEach(detailsRow => detailsRow.remove());
                if (placeholder && placeholder.parentNode) {
                    placeholder.parentNode.insertBefore(draggedRow, placeholder);
                    placeholder.parentNode.removeChild(placeholder);
                }
                placeholder = null;
                lastTargetRow = null;
                updateCopyLines();
            }
        });
    
        // دعم أجهزة اللمس (Touch Devices مثل الآيباد)
        bidLinesTableBody.addEventListener('touchstart', (e) => {
            const touch = e.touches[0];
            touchStartX = touch.clientX;
            touchStartY = touch.clientY;
            draggedRow = e.target.closest('tr');
            if (draggedRow) {
                draggedRow.classList.add('dragging'); // إضافة كلاس لتحديد الصف اللي بيتحرك
                placeholder = document.createElement('tr');
                placeholder.className = 'drag-placeholder';
                placeholder.innerHTML = '<td colspan="12"></td>';
            }
        });
    
        bidLinesTableBody.addEventListener('touchmove', (e) => {
            e.preventDefault(); // منع التمرير الافتراضي أثناء اللمس
            const touch = e.touches[0];
            const touchX = touch.clientX;
            const touchY = touch.clientY;
    
            const targetRow = document.elementFromPoint(touchX, touchY)?.closest('tr');
            if (targetRow && targetRow !== draggedRow && !targetRow.classList.contains('details-row')) {
                if (lastTargetRow !== targetRow) {
                    lastTargetRow = targetRow;
                    if (placeholder && placeholder.parentNode) {
                        placeholder.parentNode.removeChild(placeholder);
                    }
                    const rect = targetRow.getBoundingClientRect();
                    const midY = rect.top + (rect.height / 2);
                    if (touchY < midY) {
                        targetRow.parentNode.insertBefore(placeholder, targetRow);
                    } else {
                        targetRow.parentNode.insertBefore(placeholder, targetRow.nextSibling);
                    }
                    setTimeout(() => {
                        placeholder.classList.add('visible');
                    }, 10);
                }
            }
        });
    
        bidLinesTableBody.addEventListener('touchend', (e) => {
            if (draggedRow && placeholder && placeholder.parentNode) {
                const touch = e.changedTouches[0];
                const touchX = touch.clientX;
                const touchY = touch.clientY;
                const targetRow = document.elementFromPoint(touchX, touchY)?.closest('tr');
                if (targetRow && draggedRow !== targetRow && !targetRow.classList.contains('details-row')) {
                    document.querySelectorAll('.details-row').forEach(detailsRow => detailsRow.remove());
                    placeholder.parentNode.insertBefore(draggedRow, placeholder);
                    placeholder.parentNode.removeChild(placeholder);
                    updateCopyLines();
                }
            }
            draggedRow?.classList.remove('dragging');
            draggedRow = null;
            placeholder = null;
            lastTargetRow = null;
        });
    }

    // دالة منفصلة لتهيئة جدول الأيام في Bid Sheet
    function resetBidDutyTimeline() {
        const bidDutyTimeline = document.getElementById('bid-duty-timeline');
        bidDutyTimeline.innerHTML = '';
        const daysInPeriod = parseInt(bidDutyTimeline.style.minWidth) / 80;
        for (let day = 0; day <= daysInPeriod; day++) {
            const separator = document.createElement('div');
            separator.className = 'day-separator';
            separator.style.left = `${day * 80}px`;
            separator.style.height = '34px';
            bidDutyTimeline.appendChild(separator);
        }
    }

    // دالة تحديث جدول الأيام في Bid Sheet
    function updateBidDutyTimeline(pairings, lineDuties) {
        const bidDutyTimeline = document.getElementById('bid-duty-timeline');
        resetBidDutyTimeline(); // تهيئة جدول الأيام

        const localAirports = ['JED', 'RUH', 'MED', 'NUM', 'DMM'];
        const dayMap = {};
        const occupiedDays = new Set();

        const periodStartDate = new Date(periodStart + "T00:00:00Z"); // تحويل periodStart إلى كائن Date
        const daysInPeriod = parseInt(bidDutyTimeline.style.minWidth) / 80;

        pairings.forEach(pairing => {
            if (pairing.details !== "Not Found" && pairing.start_date && pairing.end_date) {
                try {
                    const startDate = new Date(pairing.start_date + "T00:00:00Z");
                    const endDate = new Date(pairing.end_date.endsWith('Z') ? pairing.end_date : pairing.end_date + "Z");

                    // حساب الفرق بالأيام بين start_date و period_start
                    const timeDiff = startDate - periodStartDate;
                    const dayStart = Math.floor(timeDiff / (1000 * 60 * 60 * 24));
                    const endTimeDiff = endDate - periodStartDate;
                    const dayEnd = Math.floor(endTimeDiff / (1000 * 60 * 60 * 24));
                    const isSameDay = startDate.toISOString().split('T')[0] === endDate.toISOString().split('T')[0];
                    const effectiveDayEnd = isSameDay ? dayStart : dayEnd;

                    for (let day = dayStart; day <= effectiveDayEnd; day++) {
                        occupiedDays.add(day + 1); // +1 لأن الأيام في duties تبدأ من 1
                    }

                    if (!dayMap[dayStart]) dayMap[dayStart] = { starts: [], ends: [] };
                    if (!isSameDay && !dayMap[effectiveDayEnd]) dayMap[effectiveDayEnd] = { starts: [], ends: [] };
                    dayMap[dayStart].starts.push(pairing);
                    if (!isSameDay) dayMap[effectiveDayEnd].ends.push(pairing);

                    const margin = 2;
                    let leftPosition = (80 * dayStart) + margin;
                    let width;

                    let reportHour = 0;
                    if (pairing.report_time) {
                        const reportTime = pairing.report_time;
                        const timeParts = reportTime.replace('Z', '').replace(':', '.').split('.');
                        const hours = parseInt(timeParts[0], 10);
                        const minutes = parseInt(timeParts[1] || '0', 10);
                        reportHour = hours + minutes / 60;
                    } else {
                        reportHour = startDate.getUTCHours() + startDate.getUTCMinutes() / 60;
                    }

                    const endHour = endDate.getUTCHours() + endDate.getUTCMinutes() / 60;

                    if (isSameDay) {
                        if (reportHour >= 12) {
                            leftPosition += 40;
                            width = 40 - (2 * margin);
                        } else if (endHour < 12) {
                            width = 40 - (2 * margin);
                        } else {
                            width = 80 - (2 * margin);
                        }
                    } else {
                        const fullDaysBetween = effectiveDayEnd - dayStart - 1;
                        width = (fullDaysBetween >= 0 ? fullDaysBetween * 80 : 0) + (reportHour >= 12 ? 40 : 80) + (endHour < 12 ? 40 : 80) - (2 * margin);
                        leftPosition += (reportHour >= 12 ? 40 : 0);
                    }

                    const duty = document.createElement('div');
                    duty.className = 'duty Flight';
                    duty.style.left = `${leftPosition}px`;
                    duty.style.minWidth = `${width}px`;
                    duty.style.width = `${width}px`;
                    duty.style.top = '4px';
                    duty.style.height = '26px';
                    duty.dataset.pairingNo = pairing.number;

                    let displayText = pairing.number;
                    if (pairing.details) {
                        const lines = pairing.details.split('\n');
                        const layovers = [];
                        for (const line of lines) {
                            const layoverMatch = line.match(/LAYOVER\s+(\w{3})\s+(\d{2}\.\d{2})/);
                            if (layoverMatch) {
                                const city = layoverMatch[1];
                                const time = layoverMatch[2];
                                const [hours, minutes] = time.split('.').map(Number);
                                const duration = hours + minutes / 60;
                                layovers.push({ city, duration });
                            }
                        }

                        let firstDestination = '';
                        for (const line of lines) {
                            const flightMatch = line.match(/^[A-Z]{2}\s+(?:DH)?\d{3,4}\s+\w{3}\s+\d{2}\.\d{2}\s+\w{3}\s+\d{2}\.\d{2}\s+(\w{3})/);
                            if (flightMatch) {
                                firstDestination = flightMatch[1];
                                break;
                            }
                        }

                        if (layovers.length > 0) {
                            const hasInternationalLayover = layovers.some(layover => !localAirports.includes(layover.city));
                            if (hasInternationalLayover) {
                                const firstInternationalLayover = layovers.find(layover => !localAirports.includes(layover.city));
                                if (firstInternationalLayover) {
                                    displayText = firstInternationalLayover.city;
                                }
                            } else {
                                const uniqueLayoverCities = [...new Set(layovers.map(layover => layover.city))];
                                const layoverCities = uniqueLayoverCities.join(', ');
                                if (firstDestination) {
                                    displayText = `${firstDestination} (${layoverCities})`;
                                } else if (layoverCities) {
                                    displayText = layoverCities;
                                }
                            }
                        } else if (firstDestination) {
                            displayText = firstDestination;
                        }
                    }

                    duty.textContent = displayText;
                    duty.addEventListener('click', () => showBidPairingDetails(pairing));
                    bidDutyTimeline.appendChild(duty);
                } catch (error) {
                    console.error(`Error rendering pairing #${pairing.number}:`, error);
                }
            }
        });

        const otherDuties = [];
        if (Array.isArray(lineDuties)) {
            const duties = Array(daysInPeriod).fill(null);
            lineDuties.forEach((duty, index) => {
                if (index < daysInPeriod) {
                    duties[index] = duty;
                }
            });

            duties.forEach((duty, index) => {
                const day = index + 1;
                if (!occupiedDays.has(day)) {
                    if (duty && duty !== '-' && duty !== '<' && duty !== '') {
                        let displayText = duty;
                        if (duty === '*') {
                            displayText = 'OFF';
                        } else if (duty === 'R') {
                            displayText = 'RES';
                        } else if (/^[A-Z]{3}$/.test(duty) && duty !== 'RES') {
                            return;
                        }
                        otherDuties.push({ day, displayText });
                    }
                }
            });
        }

        otherDuties.forEach(duty => {
            const day = duty.day;
            const displayText = duty.displayText;

            const margin = 2;
            const leftPosition = (80 * (day - 1)) + margin;
            const width = 80 - (2 * margin);

            const dutyElement = document.createElement('div');
            dutyElement.className = `duty ${displayText === 'OFF' ? 'DaysOff' : displayText === 'RES' ? 'StandBy' : 'Unknown'}`;
            dutyElement.style.left = `${leftPosition}px`;
            dutyElement.style.minWidth = `${width}px`;
            dutyElement.style.width = `${width}px`;
            dutyElement.style.top = '4px';
            dutyElement.style.height = '26px';
            dutyElement.textContent = displayText;

            bidDutyTimeline.appendChild(dutyElement);
        });
    }

    function showBidPairingDetails(pairing) {
        const modalBody = document.getElementById('bidPairingModalBody');
        modalBody.innerHTML = '';
        const block = document.createElement('div');
        block.classList.add('pairing-block');

        if (pairing.details === "Not Found") {
            block.textContent = `Pairing #${pairing.number}: Not Found`;
        } else {
            const dateParts = pairing.start_date.split('-');
            const formattedDate = `${dateParts[2]}-${dateParts[1]}-${dateParts[0]}`;
            const formattedTime = `${pairing.report_time}Z`;
            const lines = pairing.details.split('\n');
            let formattedDetails = `<div class="report-line">REPORT ON ${formattedDate} AT ${formattedTime}</div>`;
            lines.slice(1).forEach(line => {
                if (line.includes('REPORT AT')) return;
                if (line.includes('CREDIT')) {
                    formattedDetails += `<div class="credit-line">${line}</div>`;
                    formattedDetails += `<div class="min-rest-line">Time to next flight: ${pairing.minimum_rest}</div>`;
                } else if (line.includes('LAYOVER')) {
                    const cleanedLine = line.trimStart();
                    let layoverClass = 'layover-less-24';
                    const layoverMatch = line.match(/LAYOVER\s+\w{3}\s+(\d{2}\.\d{2})/);
                    if (layoverMatch) {
                        const time = layoverMatch[1];
                        const [hours, minutes] = time.split('.').map(Number);
                        const layoverDuration = hours + minutes / 60;
                        if (layoverDuration < 24) layoverClass = 'layover-less-24';
                        else if (layoverDuration <= 39) layoverClass = 'layover-24-39';
                        else if (layoverDuration <= 68) layoverClass = 'layover-39-68';
                        else layoverClass = 'layover-more-68';
                    }
                    formattedDetails += `<div class="layover-line ${layoverClass}">${cleanedLine}</div>`;
                } else if (line.trim()) {
                    const parts = line.trim().split(/\s+/);
                    const flightLine = parts.map(part => `<span class="flight-part">${part}</span>`).join('');
                    formattedDetails += `<div class="flight-line">${flightLine}</div>`;
                }
            });
            block.innerHTML = formattedDetails;
        }
        modalBody.appendChild(block);

        // إظهار النافذة الفرعية مع الـ backdrop الخاص بها
        $('#bidPairingModal').modal({
            backdrop: true,
            keyboard: true,
            show: true
        });

        // إزالة الـ backdrop الخاص بالنافذة الفرعية عند الإغلاق
        $('#bidPairingModal').on('hidden.bs.modal', function () {
            const backdrops = document.querySelectorAll('.modal-backdrop');
            if (backdrops.length > 1) {
                backdrops[backdrops.length - 1].remove(); // إزالة الـ backdrop العلوي فقط
            }
        });
    }

    function formatCarryOver(minutes) {
        if (!minutes || minutes === 0) return '00:00';
        const hours = Math.floor(minutes / 60);
        const mins = Math.round(minutes % 60); // تقريب الدقائق لتجنب الأرقام العشرية
        return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
    }

    function formatLayovers(layovers) {
        const localAirports = ['JED', 'RUH', 'MED', 'NUM', 'DMM'];
        return layovers
            .filter(layover => !localAirports.includes(layover.split(': ')[0]))
            .map(layover => {
                const [city, time] = layover.split(': ');
                const [hours, minutes] = time.split(':').map(Number);
                const totalHours = hours + minutes / 60;
                let className = '';
                if (totalHours < 24) className = 'layover-less-24';
                else if (totalHours <= 39) className = 'layover-24-39';
                else if (totalHours <= 68) className = 'layover-39-68';
                else className = 'layover-more-68';
                return `<span class="layover-span ${className}">${city} ${time}</span>`;
            })
            .join(' ');
    }

    function updateCopyLines() {
        const lineNumbers = Array.from(document.getElementById('bid-lines-table-body').querySelectorAll('tr'))
            .filter(row => !row.classList.contains('details-row')) // تجاهل صفوف التفاصيل
            .map(row => row.cells[1].textContent.trim());
        const copyLinesBtn = document.getElementById('copy-lines-btn');
        copyLinesBtn.textContent = `Copy Lines (${lineNumbers.length})`;
        copyLinesBtn.dataset.lines = lineNumbers.join(', ');
        copyLinesBtn.onclick = () => {
            navigator.clipboard.writeText(copyLinesBtn.dataset.lines);
            alert('Line numbers copied to clipboard!');
        };
        selectedLinesOrder = lineNumbers; // تحديث الترتيب النهائي بعد السحب
    }

    // حدث النقر لزر Clear Lines
    document.getElementById('clear-lines-btn').addEventListener('click', () => {
        // إلغاء تحديد جميع اللاينات في جدول Bid Sheet
        const bidLinesTableBody = document.getElementById('bid-lines-table-body');
        const checkboxes = bidLinesTableBody.querySelectorAll('.select-line');
        checkboxes.forEach(checkbox => {
            checkbox.checked = false;
        });

        // إزالة جميع اللاينات من جدول Bid Sheet
        bidLinesTableBody.innerHTML = '';

        // إلغاء تحديد الـ checkboxes في جدول الواجهة الرئيسية
        const mainTableRows = document.getElementById('lines-table-body').querySelectorAll('tr');
        mainTableRows.forEach(row => {
            const checkbox = row.querySelector('.select-line');
            if (checkbox) {
                checkbox.checked = false;
            }
        });

        // إفراغ قوائم اللاينات المختارة
        selectedLines = [];
        selectedLinesOrder = [];

        // تحديث زر Bid Sheet ليعكس العدد الجديد (0)
        updateBidSheetButton();

        // تحديث زر Copy Lines
        updateCopyLines();
    });
});