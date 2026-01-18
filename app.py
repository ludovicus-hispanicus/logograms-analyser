import streamlit as st
import pandas as pd
import plotly.express as px
import json
import re

# --- Configuration ---
st.set_page_config(
    page_title="Mesopotamian Omen Analyzer",
    page_icon="🏺",
    layout="wide",
)

# --- CSS Loading ---
def load_css(file_name="style.css"):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning("style.css not found. Falling back to default styles.")

load_css()

# --- Core Logic: Annotation ---

LOGOGRAM_PARTICLES = {'DIŠ', 'BAD', 'BE', 'UD'}

# Mapping for Diachronic Analysis
PERIOD_TO_YEAR_MAP = {
    "Old Babylonian": -1800,
    "Mittel Babylonian": -1200,
    "Middle Babylonian": -1200,
    "Neo Babylonian": -600,
    "Neo-Assyrian": -700,
    "Old Assyrian": -1900,
    "Middle Assyrian": -1100,
}

def get_token_type(token):
    # Rule 1: Logograms (All caps OR specific particles)
    # Check if purely uppercase alphabetic sequences (ignoring punctuation for check if needed, 
    # but simplest is .isupper() which works for "GUD")
    # Clean token for check? The prompt implies "Tokens" are space separated.
    # We might have punctuation attached. For now, we'll check the token as is.
    if token in LOGOGRAM_PARTICLES:
        return "logogram"
    if token.isupper():
        return "logogram"
    
    # Rule 2: Phonetic (Contains lowercase)
    # "i-na-at", "šum-ma"
    if any(c.islower() for c in token):
        return "phonetic"
    
    return "other" # Fallback

def annotate_omen(text, omen_id, period="Unspecified"):
    tokens = text.strip().split()
    annotations = []
    for i, token in enumerate(tokens):
        t_type = get_token_type(token)
        annotations.append({
            "token": token,
            "type": t_type,
            "omen_id": omen_id,
            "period": period,
            "index": i
        })
    return annotations

def calculate_ldi(annotations, exclude_particles=False):
    if not annotations:
        return 0.0
    
    logogram_count = 0
    total_tokens = 0
    
    for ann in annotations:
        if ann['type'] == 'other':
            continue # specific to prompt? Prompt says "count(logograms) / total_tokens". 
                     # Usually total_tokens includes everything, or just words? 
                     # Let's assume Valid Tokens (Logogram + Phonetic).
        
        # Check exclusion
        if exclude_particles and ann['token'] in LOGOGRAM_PARTICLES and ann['type'] == 'logogram':
            continue

        if ann['type'] == 'logogram':
            logogram_count += 1
        
        total_tokens += 1
        
    if total_tokens == 0:
        return 0.0
        
    return logogram_count / total_tokens

# --- Helper: Mock Data ---
def generate_mock_data():
    # 50 omens spread across 1000 years
    # OB (Old Babylonian) ~ -1800 -> Less logograms
    # NA (Neo-Assyrian) ~ -700 -> More logograms
    mock_data = []
    periods = ["Old Babylonian", "Middle Babylonian", "Middle Assyrian", "Neo-Assyrian"]
    
    # We'll just generate synthetic points for the trend line
    import random
    
    years = sorted(random.sample(range(-2000, -600), 50))
    
    for i, year in enumerate(years):
        # Linearly increase prob of logogram
        # Normalized time: 0 (at -2000) to 1 (at -600)
        norm_time = (year - (-2000)) / 1400
        ldi_target = 0.3 + (0.5 * norm_time) # 0.3 to 0.8
        
        # Determine period label roughly
        if year < -1595: period = "Old Babylonian"
        elif year < -1155: period = "Middle Babylonian"
        elif year < -911: period = "Middle Assyrian"
        else: period = "Neo-Assyrian"
        
        # Create a dummy entry just for the chart - wait, the chart needs LDI.
        # We can either generate full tokens OR just store the computed LDI for the mock CSV.
        # The prompt asks for "Mock CSV with 50 omens", implying we might need text?
        # "Generate a mock CSV ... to demonstrate the trend line."
        # For simplicity, let's create a DataFrame with 'Period', 'Year', 'LDI' directly if this function is called for the CSV download.
        # But if it's for the app internal flow, we need annotations.
        # Let's mock the annotations structure to feed the LDI calculator? 
        # Actually easier to just return a DataFrame for the trend demo.
        pass # Will implement in the UI part
    
    return []

# --- UI Setup ---

st.title("Mesopotamian Omen Diachronic Analyzer")
st.markdown("### A Digital Tool for Analyzing Logographic Density in Cuneiform Omen Texts")

# Sidebar
with st.sidebar:
    st.header("Settings")
    exclude_particles = st.checkbox("Exclude Particles (BE, etc.)", value=False)
    
    # Date Range Slider (Visual for now, or filters if data has 'Year' column)
    year_range = st.slider("Filter by Year (Approximation)", -2000, -600, (-2000, -600))
    
    st.markdown("---")
    st.subheader("Data Input")
    uploaded_files = st.file_uploader("Upload Omen Text(s) (.txt)", type="txt", accept_multiple_files=True)
    
    use_sample = st.button("Load Sample Data (OB vs NA)")
    
# State Management
if 'annotations' not in st.session_state:
    st.session_state['annotations'] = []

# Logic: Load Data
if use_sample:
    # Clear current
    st.session_state['annotations'] = []
    
    # Sample 1: OB
    ob_text = "šum-ma a-wi-lum i-na-at GUD"
    st.session_state['annotations'].extend(annotate_omen(ob_text, 1, "Old Babylonian"))
    
    # Sample 2: NA
    na_text = "BE ŠU.SI im-ni KUR"
    st.session_state['annotations'].extend(annotate_omen(na_text, 2, "Neo-Assyrian"))

elif uploaded_files:
    # Process multiple files
    all_anns = []
    
    # We want to reset annotations on new upload or append? 
    # Usually users expect a fresh start when uploading.
    # We will reset for simple workflow.
    current_omen_id = 1
    
    for uploaded_file in uploaded_files:
        # Infer period from filename
        # e.g. "old_babylonian.txt" -> "Old Babylonian"
        filename = uploaded_file.name
        provisional_period = filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()
        
        stringio = uploaded_file.getvalue().decode("utf-8")
        lines = stringio.splitlines()
        
        for line in lines:
            if line.strip():
                all_anns.extend(annotate_omen(line, current_omen_id, provisional_period))
                current_omen_id += 1
                
    st.session_state['annotations'] = all_anns

# --- UI: Editor & Dashboard ---

if st.session_state['annotations']:
    
    # 1. Editor
    st.subheader("Annotation Editor")
    
    # Convert list of dicts to DataFrame for editing
    df = pd.DataFrame(st.session_state['annotations'])
    
    # We want to allow editing 'type'. 
    # st.data_editor is perfect.
    
    edited_df = st.data_editor(
        df,
        column_config={
            "type": st.column_config.SelectboxColumn(
                "Token Type",
                help="The category of the token",
                width="medium",
                options=[
                    "logogram",
                    "phonetic",
                    "other"
                ],
                required=True,
            )
        },
        disabled=["token", "omen_id", "period", "index"],
        use_container_width=True,
        hide_index=True,
        key="editor"
    )
    
    # Update Session State based on Editor
    # Note: st.data_editor returns the edited dataframe. 
    # We can use this for calculations directly.
    
    # 2. Results Dashboard
    st.subheader("Analysis Results")
    
    col1, col2 = st.columns([1, 2])
    
    # Recalculate LDI based on edited_df
    # We need to group by Omen or Period to show meaningful stats?
    # Global LDI
    
    # Helper to calc LDI from df
    def calc_df_ldi(dframe):
        # filter 'other' if needed? 
        # Using same logic as function above
        relevant = dframe[dframe['type'] != 'other']
        if exclude_particles:
             # This requires filtering based on token content + type
             # We can do:
             particles_mask = (relevant['token'].isin(LOGOGRAM_PARTICLES)) & (relevant['type'] == 'logogram')
             relevant = relevant[~particles_mask]
             
        if len(relevant) == 0: return 0.0
        
        logs = relevant[relevant['type'] == 'logogram']
        return len(logs) / len(relevant)

    current_ldi = calc_df_ldi(edited_df)
    
    with col1:
        st.metric(label="Global Logographic Density Index (LDI)", value=f"{current_ldi:.3f}")
        
        # Download Button
        json_str = edited_df.to_json(orient="records", indent=2)
        st.download_button(
            label="Download Corrections (JSON)",
            data=json_str,
            file_name="annotated_oms.json",
            mime="application/json"
        )
        
    with col2:
        # Chart
        # Recalculate Logic for Trends
        # Group by Period
        chart_df = edited_df[edited_df['type'] != 'other'].copy()
        if exclude_particles:
            chart_df = chart_df[~((chart_df['token'].isin(LOGOGRAM_PARTICLES)) & (chart_df['type'] == 'logogram'))]
            
        stats = chart_df.groupby('period').apply(
            lambda x: pd.Series({
                'ldi': len(x[x['type'] == 'logogram']) / len(x) if len(x) > 0 else 0,
                'count': len(x)
            })
        ).reset_index()
        
        # Add Year for sorting and plotting
        stats['year'] = stats['period'].map(PERIOD_TO_YEAR_MAP).fillna(0)
        stats = stats.sort_values('year')

        if not stats.empty:
            # 1. Bar Chart (Categorical)
            fig_bar = px.bar(
                stats, x='period', y='ldi', 
                title="LDI by Period",
                template="simple_white",
                color_discrete_sequence=['#800020'] 
            )
            fig_bar.update_layout(font_family="Source Sans 3")
            
            # 2. Line Chart (Diachronic Trend) - Only if we have valid years
            valid_trend = stats[stats['year'] != 0]
            if len(valid_trend) > 1:
                fig_line = px.line(
                    valid_trend, x='year', y='ldi', text='period',
                    title="Diachronic Trend (LDI over Time)",
                    template="simple_white",
                     color_discrete_sequence=['#2e8b57'], # Green line
                     markers=True
                )
                fig_line.update_traces(textposition="bottom right")
                fig_line.update_layout(font_family="Source Sans 3")
                
                # Show both
                st.plotly_chart(fig_line, use_container_width=True)
            
            st.plotly_chart(fig_bar, use_container_width=True)

else:
    st.info("Upload a text file or load sample data to begin.")
