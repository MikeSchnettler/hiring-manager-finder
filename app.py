import streamlit as st
import google.generativeai as genai
import requests
import json
from bs4 import BeautifulSoup
from st_paywall import add_auth

st.set_page_config(page_title="Hiring Manager Finder", page_icon="🔍")

def check_password():    
    # 1. If the user has already successfully logged in, just return True
    if st.session_state.get("password_correct", False):
        return True

    # 2. Show the login form
    st.title("🔒 Passcode Required")
    st.write("Please enter the passcode provided on LinkedIn to unlock the tool.")
    
    # Create the input field
    password_input = st.text_input("Enter Passcode", type="password")
    
    if st.button("Unlock"):
        # We compare the input directly to the secret in your secrets.toml
        if password_input == st.secrets["APP_PASSCODE"]:
            st.session_state["password_correct"] = True
            st.rerun() # Refresh the app to show the main content immediately
        else:
            st.error("🚫 Incorrect passcode. Please try again.")
            
    return False

# --- APPLY THE GATE ---
if not check_password():
    st.stop()

# API Keys from st.secrets
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SERPER_API_KEY = st.secrets["SERPER_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash-lite')

# --- FUNCTIONS ---

def scrape_job_description(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(res.text, 'html.parser')
    for s in soup(["script", "style"]): s.decompose()
    return soup.get_text(separator=' ', strip=True)[:4000]

def predict_manager_title(text):
    prompt = f"""
    Analyze this job description and return ONLY a JSON object with:
    1. 'company_name'
    2. 'department' (e.g., Engineering, Marketing)
    3. 'target_manager_title' (The most likely boss for this role)
    4. 'team_keywords' (A list of 2-3 specific nouns that define the team or product, e.g., ["Fintech", "Mobile App"])
    
    TEXT:
    {text}
    """
    response = model.generate_content(prompt)
    
    # Clean and parse the JSON
    clean_json = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(clean_json)

def find_linkedin_url(company, title, team_keywords):
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    # 1. Create a "Title Cluster" to catch variations
    # This searches for (Manager OR Director OR Head)
    title_parts = title.split()
    role_noun = title_parts[-1] if title_parts else "Manager"
    title_cluster = f'("{title}" OR "{role_noun}" OR "Director" OR "Head")'

    # 2. Build the query
    # We put the company in quotes but leave keywords loose to allow more matches
    query = f'site:linkedin.com/in/ "{company}" intitle:{title_cluster}'
    
    if team_keywords:
        # Join keywords with OR to broaden the net
        keyword_string = ' OR '.join([f'"{k}"' for k in team_keywords])
        query += f" ({keyword_string})"

    payload = json.dumps({"q": query, "num": 5})
    response = requests.post(url, headers=headers, data=payload)
    results = response.json().get('organic', [])

    # 3. WATERFALL: If no results, try a very broad search
    if not results:
        query_broad = f'site:linkedin.com/in/ "{company}" "{title}"'
        payload_broad = json.dumps({"q": query_broad, "num": 5})
        response = requests.post(url, headers=headers, data=payload_broad)
        results = response.json().get('organic', [])
        
    return results

# --- STREAMLIT UI ---

st.title("🔍 Hiring Manager Finder")
st.caption("Using AI + Google Search to find contacts for free.")

job_url = st.text_input("Paste Job URL")

if st.button("Find LinkedIn Profile"):
    with st.spinner("Analyzing Job..."):
        job_text = scrape_job_description(job_url)
        info = predict_manager_title(job_text)
        
    with st.spinner(f"Searching for {info['target_manager_title']} at {info['company_name']}..."):
        contact_results = find_linkedin_url(info['company_name'], info['target_manager_title'], info['team_keywords'])
        
        if contact_results:
            st.success(f"🎯 Found potential managers for the {info['department']} team")
            
            # We loop through the top 3 results and create a 'Card' for each
            for idx, person in enumerate(contact_results[:5]):
                with st.container(border=True):
                    col_text, col_link = st.columns([4, 1], vertical_alignment="center")
                    
                    with col_text:
                        st.subheader(person.get('title').split('|')[0].strip()) # Cleans up "Name | LinkedIn"
                        st.caption(f"**Relevance:** {info['department']} context matched")
                        st.write(person.get('snippet'))
                    
                    with col_link:
                        st.link_button("Profile", person.get('link'), use_container_width=True)
        else:
            st.error("No specific team matches found. Try a broader search.")