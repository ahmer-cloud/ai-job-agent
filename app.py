import streamlit as st
import fitz  # PyMuPDF
import docx
import json
import io
from PIL import Image
import pytesseract
from groq import Groq

st.set_page_config(page_title="AI Job Applicant Agent", page_icon="🧑‍💼")

st.title("🧑‍💼 AI Job Applicant Agent")
st.write("Upload your resume and paste a job description. The AI will check your ATS score and missing skills.")

# ---- Get API key ----
try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    api_key = st.text_input("Enter your Groq API Key", type="password")

client = None
if api_key:
    client = Groq(api_key=api_key)


def ocr_image(image: Image.Image) -> str:
    """Run OCR on a PIL image and return extracted text."""
    try:
        return pytesseract.image_to_string(image)
    except Exception:
        return ""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF. Falls back to OCR per page if no selectable text is found."""
    text_parts = []
    pdf = fitz.open(stream=file_bytes, filetype="pdf")

    for page in pdf:
        page_text = page.get_text().strip()
        if page_text:
            text_parts.append(page_text)
        else:
            # No selectable text on this page -> likely scanned/image. Run OCR.
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            ocr_text = ocr_image(image)
            if ocr_text.strip():
                text_parts.append(ocr_text)

    pdf.close()
    return "\n".join(text_parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX: paragraphs, tables, and any embedded images (via OCR)."""
    document = docx.Document(io.BytesIO(file_bytes))
    parts = [para.text for para in document.paragraphs if para.text.strip()]

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text)

    # Extract text from any images embedded in the docx via OCR
    try:
        for rel in document.part.rels.values():
            if "image" in rel.reltype:
                image_bytes = rel.target_part.blob
                image = Image.open(io.BytesIO(image_bytes))
                ocr_text = ocr_image(image)
                if ocr_text.strip():
                    parts.append(ocr_text)
    except Exception:
        pass

    return "\n".join(parts)


def extract_text_from_image(file_bytes: bytes) -> str:
    """Extract text directly from an uploaded image file via OCR."""
    image = Image.open(io.BytesIO(file_bytes))
    return ocr_image(image)


def extract_resume_text(uploaded_file) -> str:
    file_bytes = uploaded_file.read()
    name = uploaded_file.name.lower()

    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif name.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    elif name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return extract_text_from_image(file_bytes)
    else:
        return ""


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

    if raw_output.startswith("```"):
        raw_output = raw_output.strip("`")
        if raw_output.startswith("json"):
            raw_output = raw_output[4:]
        raw_output = raw_output.strip()

    return json.loads(raw_output)


# ---- UI ----
uploaded_file = st.file_uploader(
    "Upload your Resume (PDF, DOCX, or Image)",
    type=["pdf", "docx", "png", "jpg", "jpeg", "webp"]
)
job_description = st.text_area("Paste the Job Description here", height=250)

if st.button("Analyze Resume"):
    if not client:
        st.error("Please enter your Groq API key first.")
    elif not uploaded_file:
        st.error("Please upload your resume.")
    elif not job_description.strip():
        st.error("Please paste a job description.")
    else:
        with st.spinner("Reading your resume (this may take a moment for scanned files)..."):
            try:
                resume_text = extract_resume_text(uploaded_file)

                if not resume_text.strip():
                    st.error("Could not extract any text from this file. Try a clearer scan or a different file.")
                else:
                    with st.spinner("Analyzing your resume..."):
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