import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

INPUT = "Cleaned_Preprocessed_Dataset_Week1_CORRECTED.csv"   # Uses the dataset with flags
OUT_FINAL = "Cleaned_Preprocessed_Dataset_Week1_final_checked.csv"
OUT_REPORT = "validation_report_week1.csv"

df = pd.read_csv(INPUT, parse_dates=[
    'learner_signup_datetime','opportunity_end_date','date_of_birth',
    'entry_created_at','apply_date','opportunity_start_date'
], dayfirst=False)

pd.set_option('display.max_rows', 20)

print("=" * 80)
print("COMPREHENSIVE DATASET DIAGNOSTICS & CORRECTIONS - WEEK 1")
print("=" * 80)

# ----- 1) Basic diagnostics -----
print("\n" + "=" * 80)
print("1) BASIC DIAGNOSTICS")
print("=" * 80)
print(f"\nRows: {len(df)}")
print(f"Columns: {len(df.columns)}")
print(f"\nMissing engagement_lag_days (NaN): {df['engagement_lag_days'].isna().sum()}")
print(f"Negative opportunity_duration_days (should be 0): {(df['opportunity_duration_days'] < 0).sum()}")
print(f"Flags - engagement inversion: {df['flag_engagement_inversion'].sum()}")
print(f"Flags - days_before_start extreme: {df['flag_days_before_start_extreme'].sum()}")

# ----- 2) Chronology checks (critical) -----
print("\n" + "=" * 80)
print("2) CHRONOLOGY VALIDATION")
print("=" * 80)

# a) apply before signup (should match flag)
chron_inv = df[df['apply_date'].notna() & df['learner_signup_datetime'].notna() & (df['apply_date'] < df['learner_signup_datetime'])]
print(f"\nType A - apply_date < signup_date (chronology inversions): {len(chron_inv)} records")
if len(chron_inv) > 0:
    print("\nSample rows (first 5):")
    print(chron_inv[['learner_signup_datetime','apply_date','engagement_lag_days']].head(5).to_string())

# b) start > end (should be none after fix)
bad_duration = df[df['opportunity_end_date'].notna() & df['opportunity_start_date'].notna() & (df['opportunity_end_date'] < df['opportunity_start_date'])]
print(f"\nType B - opportunity_end_date < opportunity_start_date (should be 0): {len(bad_duration)}")
if len(bad_duration) > 0:
    print("\nSample rows:")
    print(bad_duration[['opportunity_start_date','opportunity_end_date']].head(5).to_string())

# c) unrealistic ages (<10 or >120)
age_issues = df[(df['age_years'].notna()) & ((df['age_years'] < 10) | (df['age_years'] > 120))]
print(f"\nType C - Age outliers (< 10 or > 120): {len(age_issues)}")
if len(age_issues) > 0:
    print("\nAge issues found:")
    print(age_issues[['first_name','date_of_birth','learner_signup_datetime','age_years']].to_string())

# d) entry_created_at vs signup year discrepancy
df['entry_year'] = df['entry_created_at'].dt.year if df['entry_created_at'].notna().any() else np.nan
df['signup_year_from_dt'] = df['learner_signup_datetime'].dt.year
year_mismatch = df[df['entry_year'].notna() & df['signup_year_from_dt'].notna() & (df['entry_year'] != df['signup_year_from_dt']) & (df['entry_year'] > df['signup_year_from_dt'])]
print(f"\nType D - entry_created_at year > signup_year (forward created): {len(year_mismatch)}")
if len(year_mismatch) > 0:
    print("\nSample rows where entry was created after signup:")
    print(year_mismatch[['learner_signup_datetime', 'entry_created_at', 'apply_date']].head(5).to_string())

# ----- 3) Fill missing buckets, standardize values -----
print("\n" + "=" * 80)
print("3) STANDARDIZATION & TYPE COERCION")
print("=" * 80)

# engagement_lag_bucket: recompute from engagement_lag_days (preserving NaN)
bins = [-0.1, 0, 7, 30, 90, 1e9]
labels = ['0', '1-7', '8-30', '31-90', '90+']
df['engagement_lag_bucket'] = pd.cut(df['engagement_lag_days'], bins=bins, labels=labels)

# ensure NaN for missing lags
df.loc[df['engagement_lag_days'].isna(), 'engagement_lag_bucket'] = np.nan

print("\nengagement_lag_bucket distribution (after recompute):")
print(df['engagement_lag_bucket'].value_counts(dropna=False).sort_index())

# ensure applied_after_start is clean
df['applied_after_start'] = df['applied_after_start'].astype(int)
print(f"\napplied_after_start distribution:")
print(df['applied_after_start'].value_counts().sort_index())

# ----- 4) Coerce types -----
print("\n" + "=" * 80)
print("4) TYPE COERCION")
print("=" * 80)

print("\nBefore type conversion:")
print(f"  signup_year dtype: {df['signup_year'].dtype}")
print(f"  signup_month dtype: {df['signup_month'].dtype}")
print(f"  age_years dtype: {df['age_years'].dtype}")

# Convert to integer types (nullable Int64 preserves NaN)
df['signup_year'] = df['signup_year'].round().astype('Int64')
df['signup_month'] = df['signup_month'].round().astype('Int64')
df['age_years'] = df['age_years'].round().astype('Int64')
df['engagement_lag_days'] = df['engagement_lag_days'].astype('float64')  # keep as float for precision
df['opportunity_duration_days'] = df['opportunity_duration_days'].astype('float64')
df['days_before_start'] = df['days_before_start'].astype('float64')

print("\nAfter type conversion:")
print(f"  signup_year dtype: {df['signup_year'].dtype}")
print(f"  signup_month dtype: {df['signup_month'].dtype}")
print(f"  age_years dtype: {df['age_years'].dtype}")

# ----- 5) Extreme outlier report -----
print("\n" + "=" * 80)
print("5) OUTLIER IDENTIFICATION")
print("=" * 80)

outlier_candidates = df[(df['flag_days_before_start_extreme'] == 1) | (df['flag_engagement_inversion'] == 1)].copy()
outlier_candidates.to_csv("outlier_candidates_week1.csv", index=False)
print(f"\nOutlier candidates (extreme days_before_start OR engagement inversion): {len(outlier_candidates)}")
print("\nOutlier candidates sample (first 10):")
print(outlier_candidates[['apply_date', 'opportunity_start_date', 'days_before_start', 'engagement_lag_days', 'flag_engagement_inversion', 'flag_days_before_start_extreme']].head(10).to_string())

# ----- 6) Quick visuals -----
print("\n" + "=" * 80)
print("6) GENERATING VISUALIZATIONS")
print("=" * 80)

# a) Valid vs invalid engagement_lag_days
valid_count = df['engagement_lag_days'].notna().sum()
invalid_count = df['flag_engagement_inversion'].sum()
print(f"\nengagement_lag_days - Valid: {valid_count}, Invalid (flagged): {invalid_count}")

plt.figure(figsize=(5, 4))
plt.bar(['Valid', 'Invalid (NaN)'], [valid_count, invalid_count], color=['#2ecc71', '#e74c3c'])
plt.title('engagement_lag_days: Valid vs Invalid', fontsize=12, fontweight='bold')
plt.ylabel('Count')
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig("engagement_valid_invalid.png", dpi=150, bbox_inches='tight')
plt.close()
print("✓ Saved: engagement_valid_invalid.png")

# b) days_before_start distribution (capped)
plt.figure(figsize=(6, 4))
days_capped = df['days_before_start'].clip(lower=-500, upper=500).dropna()
plt.hist(days_capped, bins=50, color='#3498db', edgecolor='black', alpha=0.7)
plt.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Applied on start date')
plt.title('days_before_start Distribution (clipped -500 to +500)', fontsize=12, fontweight='bold')
plt.xlabel('Days before program start')
plt.ylabel('Frequency')
plt.legend()
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig("days_before_start_hist.png", dpi=150, bbox_inches='tight')
plt.close()
print("✓ Saved: days_before_start_hist.png")

# c) engagement_lag_bucket distribution
plt.figure(figsize=(6, 4))
bucket_counts = df['engagement_lag_bucket'].value_counts().sort_index()
plt.bar(range(len(bucket_counts)), bucket_counts.values, color='#9b59b6', edgecolor='black', alpha=0.7)
plt.xticks(range(len(bucket_counts)), bucket_counts.index, rotation=45)
plt.title('engagement_lag_bucket Distribution', fontsize=12, fontweight='bold')
plt.ylabel('Count')
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig("engagement_lag_bucket_dist.png", dpi=150, bbox_inches='tight')
plt.close()
print("✓ Saved: engagement_lag_bucket_dist.png")

# d) Age distribution
plt.figure(figsize=(6, 4))
age_data = df['age_years'].dropna()
plt.hist(age_data, bins=40, color='#f39c12', edgecolor='black', alpha=0.7)
plt.axvline(x=age_data.median(), color='red', linestyle='--', linewidth=2, label=f'Median: {age_data.median():.0f}')
plt.title('Age Distribution', fontsize=12, fontweight='bold')
plt.xlabel('Age (years)')
plt.ylabel('Frequency')
plt.legend()
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig("age_distribution.png", dpi=150, bbox_inches='tight')
plt.close()
print("✓ Saved: age_distribution.png")

# ----- 7) Save final checked file -----
print("\n" + "=" * 80)
print("7) SAVING FINAL OUTPUTS")
print("=" * 80)

# Drop temporary column
df = df.drop(['entry_year', 'signup_year_from_dt'], axis=1, errors='ignore')

df.to_csv(OUT_FINAL, index=False)
print(f"\n✓ Saved final checked CSV: {OUT_FINAL}")

# ----- 8) Quick summary csv -----
summary = {
    'metric': [
        'total_rows',
        'missing_engagement_lag_days',
        'neg_engagement_flag',
        'days_before_start_extreme_flag',
        'neg_opportunity_duration_count',
        'chronology_inversions_apply_before_signup',
        'age_outliers',
        'engagement_lag_valid_count',
        'engagement_lag_bucket_complete_count'
    ],
    'value': [
        int(len(df)),
        int(df['engagement_lag_days'].isna().sum()),
        int(df['flag_engagement_inversion'].sum()),
        int(df['flag_days_before_start_extreme'].sum()),
        int((df['opportunity_duration_days'] < 0).sum()),
        len(chron_inv),
        len(age_issues),
        valid_count,
        df['engagement_lag_bucket'].notna().sum()
    ]
}
summary_df = pd.DataFrame(summary)
summary_df.to_csv(OUT_REPORT, index=False)
print(f"✓ Saved summary report: {OUT_REPORT}\n")
print(summary_df.to_string(index=False))

# ----- 9) Data quality summary -----
print("\n" + "=" * 80)
print("8) DATA QUALITY SUMMARY")
print("=" * 80)

total_cells = len(df) * len(df.columns)
missing_cells = df.isna().sum().sum()
completeness = ((total_cells - missing_cells) / total_cells) * 100

print(f"\nTotal cells: {total_cells:,}")
print(f"Missing cells: {missing_cells:,}")
print(f"Completeness: {completeness:.2f}%")
print(f"\nData Quality Score: {'GOOD ✅' if completeness >= 90 else 'NEEDS WORK ⚠️'}")

print("\n" + "=" * 80)
print("DIAGNOSTICS & CORRECTIONS COMPLETE")
print("=" * 80)
print("\nNext steps:")
print("1. Review outlier_candidates_week1.csv for manual inspection")
print("2. Check the generated PNG visualizations for distribution insights")
print("3. Use Cleaned_Preprocessed_Dataset_Week1_final_checked.csv for analysis")
print("4. Refer to validation_report_week1.csv for summary metrics")
