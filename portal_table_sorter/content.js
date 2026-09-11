(function () {
    const COL_STUDENT_ID = 1;
    const COL_FILES = 4;
    const COL_GRADE = 5;

    const table = document.getElementById('Table1');
    if (!table) return;

    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const dataRows = Array.from(tbody.querySelectorAll('tr'))
        .filter(r => r.id && r.id.startsWith('row_'));
    if (dataRows.length === 0) return;

    // 解析 [M/D  H:MM] 格式的時間戳，回傳可排序的整數；找不到時回傳 null
    function parseTimestamp(text) {
        const m = text.match(/\[(\d{1,2})\/(\d{1,2})\s+(\d{1,2}):(\d{1,2})\]/);
        if (!m) return null;
        return parseInt(m[1]) * 1000000
             + parseInt(m[2]) * 10000
             + parseInt(m[3]) * 100
             + parseInt(m[4]);
    }

    // 取該列最後一筆有時間戳的上傳紀錄；無上傳者回傳 Infinity（排在最後）
    function getLastUploadTime(row) {
        const cell = row.cells[COL_FILES];
        if (!cell) return Infinity;
        let last = null;
        for (const a of cell.querySelectorAll('a')) {
            const t = parseTimestamp(a.textContent);
            if (t !== null) last = t;
        }
        return last !== null ? last : Infinity;
    }

    // 判斷是否尚未給分：空的 <td> 或空的 <input>
    function hasNoGrade(row) {
        const cell = row.cells[COL_GRADE];
        if (!cell) return true;
        const input = cell.querySelector('input[type="text"]');
        if (input) return input.value.trim() === '';
        return cell.textContent.trim() === '';
    }

    function getStudentNumber(row) {
        const cell = row.cells[COL_STUDENT_ID];
        return cell ? (parseInt(cell.textContent.trim(), 10) || 0) : 0;
    }

    dataRows.sort((a, b) => {
        // 1st key：未給分排前面
        const gradeA = hasNoGrade(a) ? 0 : 1;
        const gradeB = hasNoGrade(b) ? 0 : 1;
        if (gradeA !== gradeB) return gradeA - gradeB;

        // 2nd key：上傳時間早的排前面（無上傳 = Infinity，排最後）
        const timeA = getLastUploadTime(a);
        const timeB = getLastUploadTime(b);
        if (timeA !== timeB) return timeA - timeB;

        // 3rd key：學號小的排前面
        return getStudentNumber(a) - getStudentNumber(b);
    });

    // 將排序後的 data rows 重新 append 到 tbody
    // header rows（class="title_line"）不動，留在原位
    // 同時還原交錯的底色
    dataRows.forEach((row, i) => {
        row.classList.remove('record2', 'hi_line');
        row.classList.add(i % 2 === 0 ? 'record2' : 'hi_line');
        tbody.appendChild(row);
    });
})();
