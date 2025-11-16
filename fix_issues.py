import pandas as pd
import numpy as np
from math import floor

IN_CSV = 'Cleaned_Preprocessed_Dataset_Week1_final.csv'
OUT_CSV = 'Cleaned_Preprocessed_Dataset_Week1_final_fixed.csv'
AUDIT_OUT = 'fixes_audit.csv'

# load
print('Loading', IN_CSV)
df = pd.read_csv(IN_CSV)
# keep original index as row reference
orig_index = df.index

# helper to append audit rows
audit_rows = []
def record_audit(idx, column, old, new, desc):
    audit_rows.append({'row_index': int(idx), 'column': column, 'old_value': old, 'new_value': new, 'action_description': desc})

# parse dates where possible
date_cols = ['learner_signup_datetime','date_of_birth','apply_date','opportunity_start_date','opportunity_end_date','entry_created_at']
for c in date_cols:
    if c in df.columns:
        df[c+'_parsed_for_fix'] = pd.to_datetime(df[c], errors='coerce')
    else:
        df[c+'_parsed_for_fix'] = pd.Series([pd.NaT]*len(df))

# Fix 1: recompute engagement_lag_days from parsed dates
if 'engagement_lag_days' in df.columns:
    # store old
    old_vals = df['engagement_lag_days'].copy()
else:
    df['engagement_lag_days'] = np.nan
    old_vals = pd.Series([np.nan]*len(df))

# compute new lag in days where both dates available
new_lag = (df['apply_date_parsed_for_fix'] - df['learner_signup_datetime_parsed_for_fix']).dt.days
# Where either date missing, keep NaN
# Replace computed values
for i in df.index:
    old = old_vals.at[i] if i in old_vals.index else None
    val = new_lag.at[i]
    if pd.isna(val):
        if not pd.isna(old):
            # old had value but recomputed is NaN -> record and set NaN
            record_audit(i, 'engagement_lag_days', old, np.nan, 'Recomputed lag not available (dates missing)')
            df.at[i,'engagement_lag_days'] = np.nan
        else:
            df.at[i,'engagement_lag_days'] = np.nan
    else:
        # if computed value negative, mark as NaN and record (we consider negative lag invalid)
        if val < 0:
            record_audit(i, 'engagement_lag_days', old, np.nan, 'Negative lag (apply_date < signup) — cleared to NaN')
            df.at[i,'engagement_lag_days'] = np.nan
        else:
            if pd.isna(old) or (not pd.isna(old) and int(old) != int(val)):
                record_audit(i, 'engagement_lag_days', old, int(val), 'Recomputed from dates')
            df.at[i,'engagement_lag_days'] = int(val)

# Fix 2: recompute age_years from date_of_birth and signup
if 'age_years' in df.columns:
    old_age = df['age_years'].copy()
else:
    df['age_years'] = np.nan
    old_age = pd.Series([np.nan]*len(df))

for i in df.index:
    dob = df.at[i,'date_of_birth_parsed_for_fix'] if 'date_of_birth_parsed_for_fix' in df.columns else pd.NaT
    signup = df.at[i,'learner_signup_datetime_parsed_for_fix'] if 'learner_signup_datetime_parsed_for_fix' in df.columns else pd.NaT
    old = old_age.at[i] if i in old_age.index else None
    if pd.isna(dob) or pd.isna(signup):
        # cannot compute
        if not pd.isna(old):
            record_audit(i, 'age_years', old, np.nan, 'DOB or signup missing -> set age to NaN')
            df.at[i,'age_years'] = np.nan
        else:
            df.at[i,'age_years'] = np.nan
    else:
        years = floor((signup - dob).days / 365.25)
        # plausibility
        if years < 10 or years > 120:
            record_audit(i, 'age_years', old, np.nan, f'Age {years} out of plausible range -> set to NaN')
            df.at[i,'age_years'] = np.nan
        else:
            if pd.isna(old) or int(old) != int(years):
                record_audit(i, 'age_years', old, int(years), 'Recomputed from DOB and signup')
            df.at[i,'age_years'] = int(years)

# Optionally: any other fixes? For now we'll drop the parsed helper columns and write fixed files
parsed_cols = [c for c in df.columns if c.endswith('_parsed_for_fix')]
for c in parsed_cols:
    df.drop(columns=[c], inplace=True)

# Save audit
audit_df = pd.DataFrame(audit_rows)
if not audit_df.empty:
    audit_df.to_csv(AUDIT_OUT, index=False)
    print('Saved audit of fixes to', AUDIT_OUT)
else:
    # create empty file with header
    pd.DataFrame(columns=['row_index','column','old_value','new_value','action_description']).to_csv(AUDIT_OUT, index=False)
    print('No fixes recorded; created empty', AUDIT_OUT)

# Save fixed CSV
df.to_csv(OUT_CSV, index=False)
print('Saved fixed dataset to', OUT_CSV)

# Print quick summary of fixes
print('\nFix summary:')
if not audit_df.empty:
    summary = audit_df.groupby('column').size().rename('fix_count')
    print(summary.to_string())
else:
    print('No fixes applied')
