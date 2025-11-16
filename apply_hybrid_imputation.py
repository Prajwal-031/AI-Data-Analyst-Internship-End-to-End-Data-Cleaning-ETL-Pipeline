import pandas as pd
import numpy as np

IN_CSV = 'Cleaned_Preprocessed_Dataset_Week1_final_fixed.csv'
OUT_CSV = 'Cleaned_Preprocessed_Dataset_Week1_CLEAN.csv'
AUDIT_OUT = 'full_imputation_audit.csv'

print('Loading data...')
df = pd.read_csv(IN_CSV)
orig_len = len(df)

audit_rows = []
def record_audit(idx, column, old, new, desc):
    audit_rows.append({
        'row_index': int(idx) if idx >= 0 else -1,
        'column': column,
        'old_value': str(old)[:100],
        'new_value': str(new)[:100],
        'action_description': desc
    })

print('Parsing dates...')
dates_parsed = {
    'learner_signup_datetime': pd.to_datetime(df['learner_signup_datetime'], errors='coerce'),
    'opportunity_start_date': pd.to_datetime(df['opportunity_start_date'], errors='coerce'),
    'opportunity_end_date': pd.to_datetime(df['opportunity_end_date'], errors='coerce'),
    'apply_date': pd.to_datetime(df['apply_date'], errors='coerce'),
    'date_of_birth': pd.to_datetime(df['date_of_birth'], errors='coerce'),
}

print('\nApplying HYBRID imputation...\n')

# STEP 1: Fill opportunity dates by forward/backward fill within opportunity_id groups
print('1. Forward/backward filling opportunity dates by opportunity_id group...')
if 'opportunity_id' in df.columns:
    for col in ['opportunity_start_date', 'opportunity_end_date']:
        if col in df.columns:
            old_missing = df[col].isna().sum()
            # Convert to datetime first
            df[col] = pd.to_datetime(df[col], errors='coerce')
            # ffill/bfill per group using transform to preserve index
            df[col] = df.groupby('opportunity_id')[col].transform(lambda x: x.ffill().bfill())
            new_missing = df[col].isna().sum()
            saved = old_missing - new_missing
            print(f'   {col}: {old_missing} -> {new_missing} missing (saved {saved})')
            if saved > 0:
                record_audit(-1, col, f'{old_missing} missing', f'{new_missing} missing', 
                           f'Ffill/bfill by opportunity_id; saved {saved}')
            # Convert back to string for consistency
            df[col] = df[col].astype(str).str.replace('NaT', '')

# Re-parse dates after ffill
print('\nRe-parsing dates after fill...')
dates_parsed = {
    'learner_signup_datetime': pd.to_datetime(df['learner_signup_datetime'], errors='coerce'),
    'opportunity_start_date': pd.to_datetime(df['opportunity_start_date'], errors='coerce'),
    'opportunity_end_date': pd.to_datetime(df['opportunity_end_date'], errors='coerce'),
    'apply_date': pd.to_datetime(df['apply_date'], errors='coerce'),
    'date_of_birth': pd.to_datetime(df['date_of_birth'], errors='coerce'),
}

# STEP 2: Recalculate derived numeric fields
print('\n2. Recalculating derived numeric fields...')

# opportunity_duration_days
if 'opportunity_duration_days' in df.columns:
    old_missing = df['opportunity_duration_days'].isna().sum()
    new_val = (dates_parsed['opportunity_end_date'] - dates_parsed['opportunity_start_date']).dt.days
    df['opportunity_duration_days'] = new_val
    new_missing = df['opportunity_duration_days'].isna().sum()
    saved = old_missing - new_missing
    print(f'   opportunity_duration_days: {old_missing} -> {new_missing} missing (saved {saved})')

# days_before_start
if 'days_before_start' in df.columns:
    old_missing = df['days_before_start'].isna().sum()
    new_val = (dates_parsed['opportunity_start_date'] - dates_parsed['apply_date']).dt.days
    df['days_before_start'] = new_val
    new_missing = df['days_before_start'].isna().sum()
    saved = old_missing - new_missing
    print(f'   days_before_start: {old_missing} -> {new_missing} missing (saved {saved})')

# engagement_lag_days
if 'engagement_lag_days' in df.columns:
    old_missing = df['engagement_lag_days'].isna().sum()
    new_val = (dates_parsed['apply_date'] - dates_parsed['learner_signup_datetime']).dt.days
    # clear negative lags
    new_val = new_val.where(new_val >= 0, np.nan)
    df['engagement_lag_days'] = new_val
    new_missing = df['engagement_lag_days'].isna().sum()
    saved = old_missing - new_missing
    print(f'   engagement_lag_days: {old_missing} -> {new_missing} missing (saved {saved})')

# signup_month, signup_year
if 'signup_month' in df.columns:
    old_missing = df['signup_month'].isna().sum()
    new_val = dates_parsed['learner_signup_datetime'].dt.month
    df['signup_month'] = new_val
    new_missing = df['signup_month'].isna().sum()
    saved = old_missing - new_missing
    print(f'   signup_month: {old_missing} -> {new_missing} missing (saved {saved})')

if 'signup_year' in df.columns:
    old_missing = df['signup_year'].isna().sum()
    new_val = dates_parsed['learner_signup_datetime'].dt.year
    df['signup_year'] = new_val
    new_missing = df['signup_year'].isna().sum()
    saved = old_missing - new_missing
    print(f'   signup_year: {old_missing} -> {new_missing} missing (saved {saved})')

# STEP 3: Fill sparse text fields with "Unknown"
print('\n3. Filling sparse text fields...')
for col in ['institution_name', 'current_intended_major']:
    if col in df.columns:
        old_missing = df[col].isna().sum()
        if old_missing > 0:
            df[col] = df[col].fillna('Unknown')
            new_missing = df[col].isna().sum()
            print(f'   {col}: {old_missing} -> {new_missing} missing')

# Save audit
audit_df = pd.DataFrame(audit_rows)
if not audit_df.empty:
    audit_df.to_csv(AUDIT_OUT, index=False)
    print(f'\nSaved full imputation audit ({len(audit_df)} records) to {AUDIT_OUT}')
else:
    pd.DataFrame(columns=['row_index','column','old_value','new_value','action_description']).to_csv(AUDIT_OUT, index=False)

# Save clean CSV
df.to_csv(OUT_CSV, index=False)
print(f'Saved clean dataset to {OUT_CSV}')

# Show summary
print('\n' + '='*80)
print('FINAL IMPUTATION SUMMARY')
print('='*80)

# Reload to show before/after properly
df_before = pd.read_csv(IN_CSV)
df_after = df

print('\nMissing values before vs after:')
print(f'{"Column":<35} | {"Before":>20} | {"After":>20} | {"Saved":>6}')
print('-'*95)

miss_before = df_before.isna().sum()
miss_after = df_after.isna().sum()
cols_with_issue = miss_before[miss_before > 0].index.union(miss_after[miss_after > 0].index)

total_before = 0
total_after = 0
for col in sorted(cols_with_issue):
    before = miss_before.get(col, 0)
    after = miss_after.get(col, 0)
    saved = before - after
    pct_before = (before / len(df_before)) * 100 if before > 0 else 0
    pct_after = (after / len(df_after)) * 100 if after > 0 else 0
    total_before += before
    total_after += after
    
    print(f'{col:<35} | {before:>5} ({pct_before:>5.1f}%) | {after:>5} ({pct_after:>5.1f}%) | {saved:>6}')

print('-'*95)
print(f'{"TOTAL":<35} | {total_before:>5} ({(total_before/(len(df_before)*len(df_before.columns))*100):>5.1f}%) | {total_after:>5} ({(total_after/(len(df_after)*len(df_after.columns))*100):>5.1f}%) | {total_before-total_after:>6}')

print(f'\nTotal missing cells before: {df_before.isna().sum().sum():>5}')
print(f'Total missing cells after:  {df_after.isna().sum().sum():>5}')
print(f'Cells recovered:            {df_before.isna().sum().sum() - df_after.isna().sum().sum():>5}')
print(f'\nRows: {len(df_before)} (unchanged)')
