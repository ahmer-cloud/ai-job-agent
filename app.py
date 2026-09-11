import streamlit as st
import pdfplumber
import docx
import json
from groq import Groq

st.set_page_config(page_title="AI Job Applicant Agent", page_icon="🧑‍💼")

st.title("🧑‍💼 AI Job Applicant Agent")
st.write("Upload your resume and paste a job description. The AI will check your ATS score and missing skills.")

# ---- Get API key ----
# For local testing, put your key directly below (only for testing, remove before pushing to GitHub!)
# For deployment, use Streamlit secrets instead (see instructions).
try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    api_key = st.text_input("Enter your Groq API Key", type="password")

client = None
if api_key:
    client = Groq(api_key=api_key)


def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def extract_text_from_docx(file):
    document = docx.Document(file)
    text = "\n".join([para.text for para in document.paragraphs])
    return text


def analyze_resume(resume_text, job_description):
    prompt = f"""
You are an ATS (Applicant Tracking System) and career expert.
Compare the following RESUME against the JOB DESCRIPTION.

Return ONLY a valid JSON object with these exact keys, no extra text before or after:
{{
  "ats_score": <number from 0 to 100>,
  "missing_skills": [<list of important skills/keywords from the job description that are missing in the resume>],
  "suggestions": [<list of 3-5 short, actionable suggestions to improve the resume for this job>]
}}

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
    )

    raw_output = response.choices[0].message.content.strip()

    # Clean up in case the model wraps JSON in ```json ... ```
    if raw_output.startswith("```"):
        raw_output = raw_output.strip("`")
        if raw_output.startswith("json"):
            raw_output = raw_output[4:]
        raw_output = raw_output.strip()

    return json.loads(raw_output)


# ---- UI ----
uploaded_file = st.file_uploader("Upload your Resume (PDF or DOCX)", type=["pdf", "docx"])
job_description = st.text_area("Paste the Job Description here", height=250)

if st.button("Analyze Resume"):
    if not client:
        st.error("Please enter your Groq API key first.")
    elif not uploaded_file:
        st.error("Please upload your resume.")
    elif not job_description.strip():
        st.error("Please paste a job description.")
    else:
        with st.spinner("Analyzing your resume..."):
            try:
                if uploaded_file.name.endswith(".pdf"):
                    resume_text = extract_text_from_pdf(uploaded_file)
                else:
                    resume_text = extract_text_from_docx(uploaded_file)

                if not resume_text.strip():
                    st.error("Could not extract text from the resume. Try a different file.")
                else:
                    result = analyze_resume(resume_text, job_description)

                    st.subheader("📊 ATS Score")
                    st.progress(min(max(int(result["ats_score"]), 0), 100) / 100)
                    st.write(f"**{result['ats_score']} / 100**")

                    st.subheader("❌ Missing Skills")
                    if result["missing_skills"]:
                        for skill in result["missing_skills"]:
                            st.write(f"- {skill}")
                    else:
                        st.write("No major missing skills found!")

                    st.subheader("💡 Suggestions")
                    for suggestion in result["suggestions"]:
                        st.write(f"- {suggestion}")

            except json.JSONDecodeError:
                st.error("The AI response could not be read properly. Please try again.")
            except Exception as e:
                st.error(f"Something went wrong: {e}")