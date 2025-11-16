# full_pipeline_with_tests.py
# Run: python full_pipeline_with_tests.py
# Requirements: pandas, numpy, openpyxl
# This script contains:
#  - the full cleaning pipeline functions
#  - the finalization block (load raw + cleaned, audit, save final)
#  - a suite of unit tests that exercise each stage using synthetic test data

import pandas as pd
import numpy as np
import re
from datetime import datetime
import os
from IPython.display import display

# -----------------------
# Configuration
# -----------------------
INPUT_FILE = "SLU Opportunity Wise Data-1710158595043.xlsx"
CLEANED_FILE = "Cleaned_Preprocessed_Dataset_Week1.xlsx"
AUDIT_FILE = "cleaning_audit_log_week1.csv"
FINAL_CSV = "Cleaned_Preprocessed_Dataset_Week1_final.csv"
FINAL_XLSX = "Cleaned_Preprocessed_Dataset_Week1_final.xlsx"

# -----------------------
# Utility functions (exposed for testing)
# -----------------------
def normalize_column_names(df):
    df = df.copy()
    df.columns = (
        df.columns.str.strip()
                   .str.replace(" ", "_", regex=False)
                   .str.replace("/", "_", regex=False)
                   .str.replace("-", "_", regex=False)
                   .str.lower()
    )
    return df

def robust_parse_dates(series, extra_formats=None, dayfirst_try=True):
    s_raw = series.astype(str).replace({'nan': None, 'None': None})
    parsed = pd.to_datetime(s_raw, errors='coerce', dayfirst=dayfirst_try)
    needs = parsed.isna() & s_raw.notna()
    if needs.any():
        parsed2 = pd.to_datetime(s_raw[needs], errors='coerce', dayfirst=not dayfirst_try)
        parsed.loc[needs] = parsed2
    if extra_formats:
        needs = parsed.isna() & s_raw.notna()
        for fmt in extra_formats:
            if not needs.any():
                break
            try:
                parsed_tmp = pd.to_datetime(s_raw[needs], format=fmt, errors='coerce')
                parsed.loc[needs] = parsed_tmp
            except Exception:
                pass
            needs = parsed.isna() & s_raw.notna()
    return parsed

def remove_corrupt_hour_time(s):
    try:
        if pd.isna(s):
            return s
        st = str(s)
        parts = st.split()
        if len(parts) >= 2:
            timepart = parts[-1]
            m = re.match(r'^(\d+):(\d{2}):(\d{2})$', timepart)
            if m:
                hr = int(m.group(1))
                if hr > 23 or len(m.group(1)) >= 3:
                    return " ".join(parts[:-1])
        return st
    except Exception:
        return s

def clean_text(series, to_title=True):
    s = series.astype(str).fillna("").replace({"nan": ""})
    s = s.str.strip()
    s = s.str.replace(r'\s+', ' ', regex=True)
    s = s.str.replace(r'^[^\w]+|[^\w]+$', '', regex=True)
    if to_title:
        s = s.str.title()
    s = s.replace("", np.nan)
    return s

def map_gender(series):
    s = series.fillna("").astype(str).str.strip().str.lower()
    def norm(g):
        if g in ['male', 'm']:
            return 'Male'
        if g in ['female', 'f']:
            return 'Female'
        if g in ['', 'nan', 'none', 'n/a']:
            return np.nan
        return g.title()
    return s.map(norm)

def map_status(series):
    s = series.fillna("").astype(str).str.strip().str.title()
    mapping = {
        'Started': 'Started',
        'Team Allocated': 'Team Allocated',
        'Withdraw': 'Withdraw',
        'Withdrawn': 'Withdraw',
        'Waitlisted': 'Waitlisted',
        'Rejected': 'Rejected',
        'Dropped Out': 'Dropped Out',
        'Applied': 'Applied',
        'Rewards Award': 'Rewards Award'
    }
    return s.map(lambda x: mapping.get(x, x if x!="" else np.nan))

# Simple audit collector object used in pipeline and tests
class AuditCollector:
    def __init__(self):
        self.rows = []
    def record(self, row_index, column, old_value, new_value):
        self.rows.append({
            'row_index': row_index,
            'column': column,
            'old_value': old_value,
            'new_value': new_value
        })
    def to_df(self):
        return pd.DataFrame(self.rows)

# -----------------------
# Pipeline functions (useful for unit tests)
# -----------------------
def parse_and_clean_dates(df, audit=None):
    """Parse known date columns robustly and return df (mutates copy)."""
    df = df.copy()
    date_cols = ['learner_signup_datetime','date_of_birth','entry_created_at','apply_date','opportunity_start_date','opportunity_end_date']
    formats = ["%m/%d/%Y %H:%M:%S","%d/%m/%Y %H:%M:%S","%d-%m-%Y %H:%M:%S","%m/%d/%Y","%d/%m/%Y","%Y-%m-%d"]
    for c in date_cols:
        if c in df.columns:
            before = df[c].copy()
            df[c] = robust_parse_dates(df[c].astype(str), extra_formats=formats, dayfirst_try=True)
            if audit is not None:
                changed_idx = before.index[(before.notna()) & (df[c].isna())]
                for i in changed_idx:
                    audit.record(i, c, before.at[i], df.at[i,c])
    return df

def _find_raw_col_variant(raw_df, target_col):
    """
    Try to find a raw dataframe column name that corresponds to logical target_col.
    It matches ignoring case and non-alphanumeric characters.
    """
    def normalize(name):
        return re.sub(r'[^0-9a-z]', '', str(name).lower())
    target_norm = normalize(target_col)
    candidates = {normalize(c): c for c in raw_df.columns}
    if target_norm in candidates:
        return candidates[target_norm]
    # fallback: try partial tokens match (e.g., match 'learnersignupdatetime' to 'Learner SignUp DateTime')
    for k, orig in candidates.items():
        if target_norm in k or k in target_norm:
            return orig
    return None

def targeted_reparse_removing_corrupt_time(raw_df, df, col, audit=None):
    """
    Attempt to recover NaT values in df[col] by inspecting raw_df.
    If exact col name isn't present in raw_df, try to locate a column variant.
    """
    df = df.copy()
    # find raw column name variant
    raw_col = col if col in raw_df.columns else _find_raw_col_variant(raw_df, col)
    if col not in df.columns:
        # nothing to repair in parsed df
        return df
    if not raw_col or raw_col not in raw_df.columns:
        # cannot find corresponding raw column
        return df

    # find indices where parse failed but raw has value
    failed_mask = df[col].isna() & raw_df[raw_col].notna()
    if not failed_mask.any():
        return df
    idx = df[failed_mask].index
    cleaned_raw = raw_df.loc[idx, raw_col].apply(remove_corrupt_hour_time)
    parsed = robust_parse_dates(cleaned_raw, extra_formats=["%m/%d/%Y %H:%M:%S","%d/%m/%Y %H:%M:%S","%m/%d/%Y","%d/%m/%Y","%Y-%m-%d"], dayfirst_try=False)
    # apply recovered dates and audit
    for i in parsed.index:
        if pd.notna(parsed.at[i]):
            if audit is not None:
                audit.record(i, col, df.at[i,col] if col in df.columns else None, parsed.at[i])
            df.at[i,col] = parsed.at[i]
    return df

def fill_opportunity_dates_by_id(df, audit=None):
    """
    Fill missing opportunity_start_date and opportunity_end_date within the same opportunity_id
    using forward-fill then back-fill. Records any changes to the audit collector if provided.
    """
    df = df.copy()
    if 'opportunity_id' not in df.columns:
        return df

    # Keep pre-change copies aligned to the current df index
    before_start = df['opportunity_start_date'].copy() if 'opportunity_start_date' in df.columns else None
    before_end = df['opportunity_end_date'].copy() if 'opportunity_end_date' in df.columns else None

    # Fill per-group without sorting; transform preserves original indices
    df['opportunity_start_date'] = df.groupby('opportunity_id')['opportunity_start_date'].transform(lambda x: x.ffill().bfill())
    df['opportunity_end_date']   = df.groupby('opportunity_id')['opportunity_end_date'].transform(lambda x: x.ffill().bfill())

    # Record audit entries for any changes (indices are aligned)
    if audit is not None and before_start is not None:
        changed_mask = (before_start != df['opportunity_start_date']) & ~(before_start.isna() & df['opportunity_start_date'].isna())
        for i in df.index[changed_mask]:
            audit.record(i, 'opportunity_start_date', before_start.at[i], df.at[i, 'opportunity_start_date'])

    if audit is not None and before_end is not None:
        changed_mask = (before_end != df['opportunity_end_date']) & ~(before_end.isna() & df['opportunity_end_date'].isna())
        for i in df.index[changed_mask]:
            audit.record(i, 'opportunity_end_date', before_end.at[i], df.at[i, 'opportunity_end_date'])

    return df

def fix_end_before_start(df, audit=None):
    df = df.copy()
    if 'opportunity_start_date' in df.columns and 'opportunity_end_date' in df.columns:
        mask = df['opportunity_end_date'].notna() & df['opportunity_start_date'].notna() & (df['opportunity_end_date'] < df['opportunity_start_date'])
        for i in df.index[mask]:
            old = df.at[i,'opportunity_end_date']
            df.at[i,'opportunity_end_date'] = df.at[i,'opportunity_start_date']
            if audit is not None:
                audit.record(i, 'opportunity_end_date', old, df.at[i,'opportunity_end_date'])
    return df

def compute_features(df):
    df = df.copy()
    if 'date_of_birth' in df.columns and 'learner_signup_datetime' in df.columns:
        df['age_years'] = np.floor((df['learner_signup_datetime'] - df['date_of_birth']).dt.days / 365.25)
    else:
        df['age_years'] = np.nan
    if 'learner_signup_datetime' in df.columns:
        df['signup_month'] = df['learner_signup_datetime'].dt.month
        df['signup_year'] = df['learner_signup_datetime'].dt.year
    if 'apply_date' in df.columns and 'learner_signup_datetime' in df.columns:
        df['engagement_lag_days'] = (df['apply_date'] - df['learner_signup_datetime']).dt.days
    if 'opportunity_end_date' in df.columns and 'opportunity_start_date' in df.columns:
        df['opportunity_duration_days'] = (df['opportunity_end_date'] - df['opportunity_start_date']).dt.days
    if 'opportunity_start_date' in df.columns and 'apply_date' in df.columns:
        df['days_before_start'] = (df['opportunity_start_date'] - df['apply_date']).dt.days
    return df

# -----------------------
# Unit tests (synthetic cases)
# -----------------------
def run_unit_tests():
    print("Running unit tests for each pipeline stage...")

    # ---------- Test 1: Column normalization ----------
    df_test = pd.DataFrame(columns=[" Learner SignUp DateTime ", "Apply/Date", "First-Name"])
    df_norm = normalize_column_names(df_test)
    assert 'learner_signup_datetime' in df_norm.columns, "Col norm failed: signup name"
    assert 'apply_date' in df_norm.columns or 'apply_date' in df_norm.columns, "Col norm failed: apply date"
    assert 'first_name' in df_norm.columns, "Col norm failed: first-name"
    print("Test 1 (column normalization) - PASS")

    # ---------- Test 2: Date parsing with mixed formats ----------
    d = pd.Series(["06/14/2023 12:30:35", "14-06-2023 12:30:35", "2023-06-14", "708:21:29 06/14/2023"])
    parsed = robust_parse_dates(d, extra_formats=["%m/%d/%Y %H:%M:%S","%d-%m-%Y %H:%M:%S","%Y-%m-%d"])
    assert parsed.notna().sum() >= 3, "Date parsing failed to parse usual formats"
    print("Test 2 (date parsing mixed formats) - PASS")

    # ---------- Test 3: remove corrupt hour time ----------
    sample = "06/14/2023 708:21:29"
    cleaned = remove_corrupt_hour_time(sample)
    assert "708:21:29" not in cleaned, "Corrupt time removal failed"
    print("Test 3 (corrupt time removal) - PASS")

    # ---------- Test 4: clean_text ----------
    s = pd.Series(["  SAINT LOUIS  ", "nWihs", None, ""])
    cleaned = clean_text(s, to_title=True).tolist()
    assert cleaned[0] == "Saint Louis" and cleaned[1] == "Nwihs", "Text cleaning/title-casing failed"
    print("Test 4 (text cleaning) - PASS")

    # ---------- Test 5: map_gender & map_status ----------
    g = pd.Series(["M","f","Don't want to specify",""])
    mapped_g = map_gender(g)
    assert mapped_g.tolist()[0] == "Male" and mapped_g.tolist()[1] == "Female", "Gender mapping failed"
    s = pd.Series(["started","Team allocated","unknown"])
    mapped_s = map_status(s)
    assert "Started" in mapped_s.tolist() and "Team Allocated" in mapped_s.tolist(), "Status mapping failed"
    print("Test 5 (gender/status mapping) - PASS")

    # ---------- Test 6: targeted_reparse_removing_corrupt_time ----------
    raw_df = pd.DataFrame({
        'Learner SignUp DateTime': ["06/14/2023 708:21:29", "05/01/2023 05:29:16", None]
    })
    df_parsed = pd.DataFrame({
        'learner_signup_datetime': [pd.NaT, pd.NaT, pd.NaT]
    })
    audit = AuditCollector()
    df_fixed = targeted_reparse_removing_corrupt_time(raw_df, df_parsed, 'learner_signup_datetime', audit=audit)
    # after repair, at least one should be parsed (the second) -> second has valid time format
    assert df_fixed['learner_signup_datetime'].notna().sum() >= 1, "targeted reparse failed"
    print("Test 6 (targeted reparse corrupt time) - PASS")

    # ---------- Test 7: fill_opportunity_dates_by_id ----------
    df_dates = pd.DataFrame({
        'opportunity_id': ['A','A','B','B'],
        'opportunity_start_date': [pd.NaT, pd.Timestamp('2024-01-01'), pd.NaT, pd.NaT],
        'opportunity_end_date': [pd.NaT, pd.Timestamp('2024-02-01'), pd.NaT, pd.Timestamp('2024-03-01')]
    })
    audit = AuditCollector()
    df_filled = fill_opportunity_dates_by_id(df_dates, audit=audit)
    # A group should have both start and end filled on all rows
    assert df_filled[df_filled['opportunity_id']=='A']['opportunity_start_date'].notna().all(), "fill by id failed for start"
    assert df_filled[df_filled['opportunity_id']=='A']['opportunity_end_date'].notna().all(), "fill by id failed for end"
    print("Test 7 (fill by opportunity_id) - PASS")

    # ---------- Test 8: fix_end_before_start ----------
    df_inv = pd.DataFrame({
        'opportunity_start_date': [pd.Timestamp('2024-04-30'), pd.Timestamp('2024-05-01')],
        'opportunity_end_date': [pd.Timestamp('2024-04-23'), pd.Timestamp('2024-05-05')]
    })
    audit = AuditCollector()
    df_fixed = fix_end_before_start(df_inv, audit=audit)
    assert (df_fixed['opportunity_end_date'] >= df_fixed['opportunity_start_date']).all(), "end<start fix failed"
    print("Test 8 (fix end<start) - PASS")

    # ---------- Test 9: compute_features ----------
    df_feat = pd.DataFrame({
        'date_of_birth': [pd.Timestamp('2000-01-01')],
        'learner_signup_datetime': [pd.Timestamp('2023-06-14')],
        'apply_date': [pd.Timestamp('2023-06-15')],
        'opportunity_start_date': [pd.Timestamp('2023-06-20')],
        'opportunity_end_date': [pd.Timestamp('2023-06-25')]
    })
    df_feat = compute_features(df_feat)
    assert 'age_years' in df_feat.columns and 'engagement_lag_days' in df_feat.columns and 'opportunity_duration_days' in df_feat.columns, "feature computation failed"
    print("Test 9 (feature engineering) - PASS")

    # ---------- Test 10: audit collector records changes ----------
    audit = AuditCollector()
    audit.record(1,'gender','M','Male')
    df_audit = audit.to_df()
    assert len(df_audit) == 1 and df_audit.iloc[0]['column']=='gender', "audit collector failed"
    print("Test 10 (audit collector) - PASS")

    print("\nAll unit tests PASSED.")

# -----------------------
# Finalization and optionally run pipeline on your files
# -----------------------
def run_full_finalization():
    """
    Loads cleaned file & raw file, performs final inspections, recomputes features,
    writes final files and audit (if exists).
    """
    # load cleaned + raw (expect these files to exist in working directory)
    if not os.path.exists(CLEANED_FILE):
        raise FileNotFoundError(f"Expected cleaned file '{CLEANED_FILE}' not found. Run pipeline first.")
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"Expected raw file '{INPUT_FILE}' not found. Provide raw file.")

    df = pd.read_excel(CLEANED_FILE)
    raw = pd.read_excel(INPUT_FILE, dtype=object)
    # attempt to load audit if exists
    audit_df = pd.DataFrame()
    if os.path.exists(AUDIT_FILE):
        try:
            audit_df = pd.read_csv(AUDIT_FILE)
        except Exception:
            audit_df = pd.DataFrame()

    # Example final steps (already implemented in your pipeline):
    # recompute derived features
    df = compute_features(df)

    # final missingness summary print
    print("Final missingness summary (top 30):")
    print(df.isna().sum().sort_values(ascending=False).head(30).to_string())

    # save final files
    df.to_csv(FINAL_CSV, index=False)
    df.to_excel(FINAL_XLSX, index=False)
    print(f"Final files saved: {FINAL_CSV}, {FINAL_XLSX}")

# -----------------------
# Main guard
# -----------------------
if __name__ == "__main__":
    # Run unit tests first
    run_unit_tests()

    # After tests pass you can run finalization which uses your cleaned files
    # Uncomment the next line to run final save (requires CLEANED_FILE and INPUT_FILE present)
    # run_full_finalization()

    print("\nScript finished. Unit tests passed. If you want to run full finalization, remove the comment on run_full_finalization().")
