#!/usr/bin/env python3
import argparse
import csv
import math
import os
from pathlib import Path

import numpy as np


CSV_ENCODINGS = ('utf-8-sig', 'cp950')

WAY_CSV_NAME = 'way.csv'
GRADE_CSV_NAME = 'grade.csv'

WAY_COL_ID = 1
WAY_COL_STATUS = 2
WAY_COL_TYPE = 4

GRADE_COL_ID = 1
GRADE_COL_STATUS = 2
GRADE_COL_SCORE = 6

STOP_KEYWORD = '停修'
TOP_RATIO = 0.3

CATEGORY_KEYWORDS = [
    ['繁星'],
    ['個人申請'],
    ['考試入學'],
    ['轉學'],
    ['僑'],
    ['外國', '國際'],
    ['APCS'],
]


def get_col(row, idx):
    return row[idx].strip() if idx < len(row) else ''


def read_csv_raw(path, col_indices, filter_col, filter_keyword):
    for encoding in CSV_ENCODINGS:
        try:
            with open(path, encoding=encoding, newline='') as f:
                raw = list(csv.reader(f))
            result = []
            for row in raw:
                if not row:
                    continue
                if filter_keyword in get_col(row, filter_col):
                    continue
                result.append([get_col(row, i) for i in col_indices])
            return result
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        '/'.join(CSV_ENCODINGS), b'', 0, 1,
        f'{Path(path).name} 無法用 UTF-8 或 Big5 解碼。',
    )


def read_way(path):
    rows = read_csv_raw(path, [WAY_COL_ID, WAY_COL_TYPE], WAY_COL_STATUS, STOP_KEYWORD)
    return {sid: type_str for sid, type_str in rows}


def read_grade(path):
    rows = read_csv_raw(path, [GRADE_COL_ID, GRADE_COL_SCORE], GRADE_COL_STATUS, STOP_KEYWORD)
    result = {}
    for sid, score_str in rows:
        try:
            result[sid] = int(score_str)
        except ValueError:
            raise ValueError(f'學號 {sid} 的成績 "{score_str}" 無法轉換為整數。')
    return result


def classify(type_str):
    for i, keywords in enumerate(CATEGORY_KEYWORDS):
        if any(kw in type_str for kw in keywords):
            return i
    return None


def parse_args():
    parser = argparse.ArgumentParser(description='課程分析資料統計表')
    parser.add_argument('dir', nargs='?', default=None, help='資料夾路徑，預設為目前工作目錄')
    parser.add_argument('--pass_score', type=int, default=60, help='及格標準，預設 60')
    return parser.parse_args()


def main():
    args = parse_args()
    base_dir = Path(args.dir) if args.dir else Path(os.getcwd())

    way_path = base_dir / WAY_CSV_NAME
    grade_path = base_dir / GRADE_CSV_NAME
    for path in (way_path, grade_path):
        if not path.exists():
            raise FileNotFoundError(f'找不到檔案：{path}')

    way_data = read_way(way_path)
    grade_data = read_grade(grade_path)

    # 檢查學號對應
    way_ids = set(way_data)
    grade_ids = set(grade_data)
    only_in_way = way_ids - grade_ids
    only_in_grade = grade_ids - way_ids
    if only_in_way or only_in_grade:
        msg = []
        if only_in_way:
            msg.append(f'只出現在 {WAY_CSV_NAME}：{sorted(only_in_way)}')
        if only_in_grade:
            msg.append(f'只出現在 {GRADE_CSV_NAME}：{sorted(only_in_grade)}')
        raise ValueError('學號不一致，' + '；'.join(msg))

    # 建立 numpy 陣列
    sids = list(way_ids)
    scores_arr = np.array([grade_data[sid] for sid in sids])
    cats_list = [classify(way_data[sid]) for sid in sids]
    cats_arr = np.array([-1 if c is None else c for c in cats_list])

    total = len(sids)
    top_n = math.floor(total * TOP_RATIO)
    sorted_scores = np.sort(scores_arr)
    top_cutoff = sorted_scores[total - top_n] if top_n > 0 else np.inf

    # 每人在全班的百分位數：(低於他的人數 + 1) / 總人數
    below_counts = np.searchsorted(sorted_scores, scores_arr, side='left')
    percentiles = (below_counts + 1) / total

    unclassified = int(np.sum(cats_arr == -1))
    n_cats = len(CATEGORY_KEYWORDS)

    cat_total = np.zeros(n_cats, dtype=int)
    cat_pass = np.zeros(n_cats, dtype=int)
    cat_top = np.zeros(n_cats, dtype=int)
    cat_percentile_sum = np.zeros(n_cats)

    for i in range(n_cats):
        mask = cats_arr == i
        cat_total[i] = np.sum(mask)
        cat_pass[i] = np.sum(scores_arr[mask] >= args.pass_score)
        cat_top[i] = np.sum(scores_arr[mask] >= top_cutoff)
        cat_percentile_sum[i] = np.sum(percentiles[mask])

    # 輸出
    print(f'及格標準：{args.pass_score}')
    print(f'有效資料總人數：{total}（含未分類 {unclassified} 人）')
    print(f'前 {TOP_RATIO * 100:.0f}% 門檻：前 {top_n} 名，成績 >= {top_cutoff}')
    print()

    for i in range(n_cats):
        n = cat_total[i]
        p = cat_pass[i]
        t = cat_top[i]
        if n == 0:
            print('0\t0\t0\t0.00%\t0.00%\t0.00%')
        else:
            avg_pct = cat_percentile_sum[i] / n
            print(f'{n}\t{p}\t{t}\t{p / n * 100:.2f}%\t{t / n * 100:.2f}%\t{avg_pct * 100:.2f}%')


if __name__ == '__main__':
    main()