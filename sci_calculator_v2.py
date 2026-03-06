"""
SCI (Staking Concentration Index) Calculator v2.1
For: IPR Paper 2 - Quantum Risk and Web3 Governance
Author: Junwon Lee

v2.1 fixes:
  - load_data(): column normalization BEFORE datetime conversion
  - Table numbering: SCI summary = Table 4 (not Table 1)
  - Category-level fallback limitation text generator
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import argparse
import os
import warnings
warnings.filterwarnings('ignore')

# ══════════════════════════════════════
# 1. DATA LOADING
# ══════════════════════════════════════

def load_data(filepath):
    """
    Load staking data CSV.
    
    FIX v2.1: Normalize column names FIRST, then convert datetime.
    This prevents KeyError when CSV has 'Date', 'Time', 'Category' etc.
    """
    df = pd.read_csv(filepath)
    
    # Step 1: Normalize ALL column names to lowercase FIRST
    df.columns = [c.lower().strip() for c in df.columns]
    
    # Step 2: Smart rename to standard columns
    rename_map = {}
    for c in df.columns:
        c_lower = c.lower()
        if c_lower in ('date', 'time', 'timestamp', 'day', 'block_date'):
            rename_map[c] = 'date'
        elif c_lower in ('category', 'entity', 'pool', 'operator', 'name', 'staker', 'depositor_entity_category'):
            rename_map[c] = 'entity'
        elif c_lower in ('staked_eth', 'eth', 'amount', 'total_eth', 'staked', 'value', 'amount_staked'):
            rename_map[c] = 'staked_eth'
    df = df.rename(columns=rename_map)
    
    # Step 3: Validate required columns exist
    required = ['date', 'entity', 'staked_eth']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"ERROR: Missing columns after rename: {missing}")
        print(f"Available columns: {df.columns.tolist()}")
        print(f"First 3 rows:\n{df.head(3)}")
        raise ValueError(f"Cannot proceed without columns: {missing}")
    
    # Step 4: NOW convert datetime (after column is properly named)
    df['date'] = pd.to_datetime(df['date'])
    
    # Step 5: Print distribution for manual review
    print("=== Entity Distribution (latest snapshot) ===")
    latest = df[df['date'] == df['date'].max()]
    dist = latest.groupby('entity')['staked_eth'].sum().sort_values(ascending=False)
    total = dist.sum()
    n_entities = len(dist)
    print(f"Total entities: {n_entities}")
    for name, val in dist.head(15).items():
        print(f"  {name}: {val:,.0f} ETH ({val/total*100:.2f}%)")
    if n_entities > 15:
        print(f"  ... and {n_entities - 15} more")
    
    # Step 6: Detect data level
    if n_entities <= 8:
        print(f"\n⚠️  WARNING: Only {n_entities} unique entities detected.")
        print("    This looks like CATEGORY-level data, not entity-level.")
        print("    W2/T4 support will be weaker. Consider adding limitation text.")
        df._data_level = 'category'
    else:
        df._data_level = 'entity'
        print(f"\n✓ Entity-level data detected ({n_entities} entities)")
    
    return df


def apply_entity_cutoff(df, top_n=10):
    """
    Keep top N entities by latest staked ETH, merge rest into 'Other'.
    Document this rule in methodology.
    """
    latest = df[df['date'] == df['date'].max()]
    top_entities = (latest.groupby('entity')['staked_eth'].sum()
                    .nlargest(top_n).index.tolist())
    
    df['entity_clean'] = df['entity'].where(
        df['entity'].isin(top_entities), 'Other'
    )
    
    print(f"\n=== Entity Cutoff: Top {top_n} kept ===")
    print(f"Kept: {top_entities}")
    
    df = (df.groupby(['date', 'entity_clean'])['staked_eth']
          .sum().reset_index()
          .rename(columns={'entity_clean': 'entity'}))
    
    return df


def resample_quarterly(df):
    """Resample to quarterly snapshots. Pivot-based (no groupby index clash)."""
    wide = (df.pivot_table(index='date', columns='entity',
                           values='staked_eth', aggfunc='sum')
            .sort_index()
            .resample('QE').last()
            .ffill()
            .fillna(0))
    return wide.stack().rename('staked_eth').reset_index()


def calc_shares(df):
    """Calculate proportional shares per entity per date."""
    # FIX: Make a clean copy and ensure fresh columns
    result = df[['date', 'entity', 'staked_eth']].copy()
    
    totals = result.groupby('date', as_index=False)['staked_eth'].sum()
    totals = totals.rename(columns={'staked_eth': 'total'})
    
    result = result.merge(totals, on='date', how='left')
    result['share'] = result['staked_eth'] / result['total']
    result['share'] = result['share'].fillna(0)
    
    return result


# ══════════════════════════════════════
# 2. SCI CALCULATIONS
# ══════════════════════════════════════

def calc_hhi(shares):
    return (shares ** 2).sum()

def calc_nakamoto(shares, threshold=1/3):
    sorted_shares = sorted(shares, reverse=True)
    cumsum = 0
    for i, s in enumerate(sorted_shares):
        cumsum += s
        if cumsum >= threshold:
            return i + 1
    return len(sorted_shares)

def calc_entropy(shares):
    shares = shares[shares > 0]
    if len(shares) == 0: return 0
    return -np.sum(shares * np.log2(shares))

def calc_norm_entropy(shares):
    shares = shares[shares > 0]
    n = len(shares)
    if n <= 1: return 0
    H = -np.sum(shares * np.log2(shares))
    return H / np.log2(n)

def compute_sci(df, label="full"):
    results = []
    for date, group in df.groupby('date'):
        shares = group['share'].values
        total = group['staked_eth'].sum()
        n_active = len(shares[shares > 0])
        results.append({
            'date': date,
            'hhi': calc_hhi(shares),
            'nakamoto': calc_nakamoto(shares),
            'entropy': calc_entropy(shares),
            'norm_entropy': calc_norm_entropy(shares),
            'total_staked_eth': total,
            'n_entities': n_active,
            'variant': label,
        })
    return pd.DataFrame(results)


# ══════════════════════════════════════
# 3. ROBUSTNESS CHECK
# ══════════════════════════════════════

def robustness_check(df):
    df_full = calc_shares(df.copy())
    sci_full = compute_sci(df_full, label="full")
    
    df_clean = df[~df['entity'].isin(['Other', 'Unknown'])].copy()
    df_clean = calc_shares(df_clean)
    sci_clean = compute_sci(df_clean, label="excl_other")
    
    sci_combined = pd.concat([sci_full, sci_clean], ignore_index=True)
    
    print("\n=== Robustness: Full vs Excl-Other (latest) ===")
    for var in ['full', 'excl_other']:
        row = sci_combined[(sci_combined['variant'] == var) & 
                           (sci_combined['date'] == sci_combined['date'].max())].iloc[0]
        print(f"  {var:12s}: HHI={row['hhi']:.4f}, NC={row['nakamoto']:.0f}, NormH={row['norm_entropy']:.3f}")
    
    return sci_combined


# ══════════════════════════════════════
# 4. VISUALIZATION
# ══════════════════════════════════════

EVENTS = {
    'Shapella': pd.Timestamp('2023-04-12'),
    'Pectra': pd.Timestamp('2025-05-07'),
}

def plot_sci_timeseries(sci_df, output_dir='figures'):
    output_path = os.path.join(output_dir, 'figure1_sci_timeseries.png')
    sci = sci_df[sci_df['variant'] == 'full'].copy().sort_values('date')
    
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    fig.suptitle('Staking Concentration Index (SCI) — Ethereum', fontsize=14, fontweight='bold')
    
    ax1 = axes[0]
    ax1.plot(sci['date'], sci['hhi'], 'b-o', markersize=4, linewidth=1.5)
    ax1.axhline(y=0.25, color='r', linestyle='--', alpha=0.5, label='Highly concentrated (0.25)')
    ax1.axhline(y=0.15, color='orange', linestyle='--', alpha=0.5, label='Moderately concentrated (0.15)')
    for name, dt in EVENTS.items():
        ax1.axvline(x=dt, color='gray', linestyle=':', alpha=0.6)
        ax1.annotate(name, xy=(dt, ax1.get_ylim()[1]*0.9), fontsize=8, rotation=90, va='top')
    ax1.set_ylabel('HHI', fontsize=11)
    ax1.legend(fontsize=9, loc='upper right')
    ax1.set_title('(a) Herfindahl-Hirschman Index (HHI)', fontsize=11, loc='left')
    ax1.grid(True, alpha=0.3)
    
    ax2 = axes[1]
    ax2.plot(sci['date'], sci['nakamoto'], 'g-s', markersize=4, linewidth=1.5)
    ax2.axhline(y=1, color='r', linestyle='--', alpha=0.5, label='Single-entity threshold')
    for name, dt in EVENTS.items():
        ax2.axvline(x=dt, color='gray', linestyle=':', alpha=0.6)
    ax2.set_ylabel('Nakamoto Coeff.', fontsize=11)
    ax2.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax2.legend(fontsize=9, loc='upper right')
    ax2.set_title('(b) Nakamoto Coefficient (1/3 threshold)', fontsize=11, loc='left')
    ax2.grid(True, alpha=0.3)
    
    ax3 = axes[2]
    ax3.plot(sci['date'], sci['norm_entropy'], 'purple', marker='^', markersize=4, linewidth=1.5)
    ax3.axhline(y=1.0, color='gray', linestyle=':', alpha=0.5, label='Maximum diversity (1.0)')
    for name, dt in EVENTS.items():
        ax3.axvline(x=dt, color='gray', linestyle=':', alpha=0.6)
    ax3.set_ylabel('Norm. Entropy', fontsize=11)
    ax3.set_xlabel('Date', fontsize=11)
    ax3.set_ylim(0, 1.05)
    ax3.legend(fontsize=9, loc='upper right')
    ax3.set_title('(c) Normalized Shannon Entropy (H/log₂N)', fontsize=11, loc='left')
    ax3.grid(True, alpha=0.3)
    
    fig.autofmt_xdate(rotation=45)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def plot_stacked_area(df, output_dir='figures'):
    output_path = os.path.join(output_dir, 'figure2_staked_by_entity.png')
    pivot = df.pivot_table(index='date', columns='entity',
                           values='staked_eth', aggfunc='sum').fillna(0)
    final = pivot.iloc[-1].sort_values(ascending=False)
    pivot = pivot[final.index]
    
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#aec7e8']
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.stackplot(pivot.index, [pivot[c] / 1e6 for c in pivot.columns],
                 labels=pivot.columns, colors=colors[:len(pivot.columns)], alpha=0.85)
    for name, dt in EVENTS.items():
        ax.axvline(x=dt, color='black', linestyle='--', alpha=0.7, linewidth=1.2)
        ax.annotate(name, xy=(dt, ax.get_ylim()[1]*0.95), fontsize=9,
                    fontweight='bold', rotation=90, va='top')
    ax.set_title('Staked ETH by Entity\nEthereum, 2020 Q4 – 2026 Q1',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel('Date', fontsize=11)
    ax.set_ylabel('Staked ETH (millions)', fontsize=11)
    ax.legend(loc='upper left', fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate(rotation=45)
    plt.tight_layout()
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


# FIX v2.1: Table numbering → Table 4 (paper: T1=SWOT, T2=Temporal, T3=TOWS)
def generate_summary_table(sci_df, output_dir='data/processed'):
    """
    Table 4 (paper body): Key-timepoint SCI summary.
    Appendix Table A1: Full quarterly SCI.
    """
    sci = sci_df[sci_df['variant'] == 'full'].copy()
    sci['quarter_label'] = sci['date'].dt.to_period('Q').astype(str)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Full quarterly → appendix
    full_table = sci[['quarter_label', 'total_staked_eth', 'hhi', 'nakamoto',
                      'norm_entropy', 'n_entities']].copy()
    full_table.columns = ['Quarter', 'Total Staked ETH', 'HHI',
                          'Nakamoto Coeff.', 'Norm. Entropy', 'Active Entities']
    full_table['Total Staked ETH'] = full_table['Total Staked ETH'].apply(lambda x: f"{x:,.0f}")
    full_table['HHI'] = full_table['HHI'].apply(lambda x: f"{x:.4f}")
    full_table['Norm. Entropy'] = full_table['Norm. Entropy'].apply(lambda x: f"{x:.3f}")
    full_path = os.path.join(output_dir, 'appendix_table_a1_sci_full.csv')
    full_table.to_csv(full_path, index=False)
    
    # Key timepoints → Table 4
    key_indices = [0, len(sci)//4, len(sci)//2, 3*len(sci)//4, len(sci)-1]
    key_indices = sorted(set(key_indices))
    key_table = sci.iloc[key_indices]
    key_out = key_table[['quarter_label', 'total_staked_eth', 'hhi',
                         'nakamoto', 'norm_entropy']].copy()
    key_out.columns = ['Quarter', 'Total Staked ETH', 'HHI',
                       'Nakamoto Coeff.', 'Norm. Entropy']
    key_out['Total Staked ETH'] = key_out['Total Staked ETH'].apply(lambda x: f"{x:,.0f}")
    key_out['HHI'] = key_out['HHI'].apply(lambda x: f"{x:.4f}")
    key_out['Norm. Entropy'] = key_out['Norm. Entropy'].apply(lambda x: f"{x:.3f}")
    key_path = os.path.join(output_dir, 'table4_sci_summary.csv')
    key_out.to_csv(key_path, index=False)
    
    print(f"Saved: {key_path} (Table 4, body)")
    print(f"Saved: {full_path} (Appendix A1)")
    print(key_out.to_string(index=False))
    return key_out


# ══════════════════════════════════════
# 5. LIMITATION TEXT GENERATOR
# ══════════════════════════════════════

def generate_limitation_text(data_level):
    """Generate appropriate methodology limitation text based on data granularity."""
    if data_level == 'category':
        return """
[INSERT IN SECTION III.2 METHODOLOGY]
"The SCI metrics are calculated at the staking-category level (liquid staking, 
exchanges, pools, solo validators) rather than at the individual-entity level 
due to data-source constraints. This aggregation may understate concentration 
within categories—particularly liquid staking, where a single protocol (Lido) 
accounts for the majority of the category share. Entity-level concentration 
within the liquid staking category is addressed qualitatively through referenced 
literature (Nabben & De Filippi, 2024)."
"""
    else:
        return """
[INSERT IN SECTION III.2 METHODOLOGY — already appropriate]
Entity-level data confirmed. Current methodology text is sufficient.
"""


# ══════════════════════════════════════
# 6. MAIN EXECUTION
# ══════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='SCI Calculator v2.1')
    parser.add_argument('--input', default='data/raw/staking_data.csv',
                        help='Path to staking CSV')
    parser.add_argument('--output-dir', default='data/processed',
                        help='Output directory for CSVs')
    parser.add_argument('--figures-dir', default='figures',
                        help='Output directory for figures')
    parser.add_argument('--top-n', type=int, default=10,
                        help='Number of top entities to keep')
    args = parser.parse_args()
    
    print("=" * 60)
    print("SCI Calculator v2.1 — Entity-Level Design")
    print("=" * 60)
    
    # Load
    df = load_data(args.input)
    data_level = getattr(df, '_data_level', 'unknown')
    
    # Limitation text
    lim_text = generate_limitation_text(data_level)
    print(lim_text)
    
    # Entity cutoff
    df = apply_entity_cutoff(df, top_n=args.top_n)
    
    # Resample
    df_q = resample_quarterly(df)
    
    # Shares
    df_q = calc_shares(df_q)
    
    # SCI + robustness
    sci_combined = robustness_check(df_q)
    
    # Outputs
    sci_full = sci_combined[sci_combined['variant'] == 'full']
    plot_sci_timeseries(sci_combined, args.figures_dir)
    plot_stacked_area(df_q, args.figures_dir)
    generate_summary_table(sci_combined, args.output_dir)
    
    # Raw results
    raw_path = os.path.join(args.output_dir, 'sci_raw_results.csv')
    sci_combined.to_csv(raw_path, index=False)
    
    # Key findings
    print("\n" + "=" * 60)
    print("KEY FINDINGS FOR PAPER")
    print("=" * 60)
    latest = sci_full.iloc[-1]
    earliest = sci_full.iloc[0]
    print(f"HHI:      {earliest['hhi']:.4f} → {latest['hhi']:.4f} "
          f"({'↑ concentrating' if latest['hhi'] > earliest['hhi'] else '↓ dispersing'})")
    print(f"Nakamoto: {earliest['nakamoto']:.0f} → {latest['nakamoto']:.0f} "
          f"({'↓ fewer needed' if latest['nakamoto'] < earliest['nakamoto'] else '↑ more needed'})")
    print(f"Norm.H:   {earliest['norm_entropy']:.3f} → {latest['norm_entropy']:.3f} "
          f"({'↓ less diverse' if latest['norm_entropy'] < earliest['norm_entropy'] else '↑ more diverse'})")
    
    # Shapella effect
    shapella = pd.Timestamp('2023-04-12')
    pre = sci_full[sci_full['date'] < shapella]
    post = sci_full[sci_full['date'] >= shapella]
    if len(pre) > 0 and len(post) > 0:
        p_row, q_row = pre.iloc[-1], post.iloc[0]
        print(f"\nShapella effect:")
        print(f"  HHI: {p_row['hhi']:.4f} → {q_row['hhi']:.4f}")
        print(f"  NC:  {p_row['nakamoto']:.0f} → {q_row['nakamoto']:.0f}")
        print(f"  NE:  {p_row['norm_entropy']:.3f} → {q_row['norm_entropy']:.3f}")
    
    print(f"\nData level: {data_level}")
    print("All outputs generated successfully.")


if __name__ == '__main__':
    main()
