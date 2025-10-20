# utils.py
import json
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from docx import Document
from flask import make_response
import re # Import regex for LaTeX processing

# --- Helper function to convert simple LaTeX to ReportLab Markup ---
def process_latex_for_reportlab(text):
    """
    Converts simple LaTeX $...$ or $$...$$ expressions into ReportLab's 
    internal markup, focusing only on expressions that look like math.
    """
    # Use a more aggressive pattern to remove unwanted dollar signs around simple numbers/text,
    # but specifically targeting the ITMML (ReportLab Markup) replacement tags.
    
    # 1. Smarter replacement for single-dollar inline math ($...$)
    # Look for $ followed by math-like characters (\, {), Greek letters, or operators.
    # If the match looks too simple (just a number or simple word), we might miss it here, 
    # but the AI is the main cause, so let's focus on translating complex syntax.
    
    # Replacement logic: If it contains spaces, it's likely mixed text/math and should be formatted.
    
    # We will use the italic tag for all replacements as before, but focus the regex on actual LaTeX.
    
    def replace_inline_latex(match):
        content = match.group(1)
        # If the content is just a simple number (e.g., $6$), treat it as normal text.
        if re.fullmatch(r'\s*\d+(\.\d+)?\s*', content):
            return content # Return content without dollar signs or italics
        # If the content contains only simple words and numbers, return as normal text.
        if re.fullmatch(r'[a-zA-Z0-9 ]+', content):
             return content 
        
        # Otherwise, treat it as math and apply italic formatting
        return f'<font name="Times-Italic" size="10">{content}</font>'


    # 1. Replace double-dollar block math (always treat as math)
    # Re-introducing basic LaTeX command replacement for better readability in PDF
    text = re.sub(r'\$\$(.*?)\$\$', lambda m: f'<br/>\n<font name="Times-Italic" size="10">{m.group(1)}</font><br/>\n', text, flags=re.DOTALL)
    
    # 2. Apply smarter replacement for single-dollar inline math
    text = re.sub(r'\$(.*?)\$', replace_inline_latex, text)
    
    # 3. Basic replacements for common LaTeX commands (Do this *after* the smart $ replacement)
    text = text.replace(r'\lim', 'lim')
    text = text.replace(r'\frac{', '(').replace('}{', '/').replace('}', ')')
    text = text.replace(r'\sum', '&sum;') # Use HTML entities for better compatibility
    text = text.replace(r'\pi', '&pi;') # Use HTML entities
    
    # 4. Handle HTML-like tags for bold text which ReportLab supports
    text = text.replace('<b>', '<b>').replace('</b>', '</b>')
    
    return text

def generate_pdf(paper_data):
    """Generate PDF version of the question paper with basic LaTeX support and correct MCQ format"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Title and Details
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=16, spaceAfter=30, alignment=1)
    story.append(Paragraph(paper_data['title'], title_style))
    story.append(Spacer(1, 12))
    
    details = f"""
    <b>Subject:</b> {paper_data['subject']}<br/>
    <b>Duration:</b> {paper_data['duration']} minutes<br/>
    <b>Total Marks:</b> {paper_data['total_marks']}<br/>
    <b>Difficulty:</b> {paper_data['difficulty'].title()}
    """
    story.append(Paragraph(details, styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Instructions
    instructions = """
    <b>Instructions:</b><br/>
    1. Read all questions carefully before answering.<br/>
    2. Answer all questions.<br/>
    3. Write clearly and legibly.<br/>
    4. Manage your time effectively.
    """
    story.append(Paragraph(instructions, styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Questions
    questions = json.loads(paper_data['questions'])['questions']
    question_num = 1
    
    for question in questions:
        # Process question text for basic LaTeX rendering
        processed_q_text = process_latex_for_reportlab(question['question'])
        
        # Question text
        q_text = f"<b>Q{question_num}. {processed_q_text}</b> ({question['marks']} marks)"
        story.append(Paragraph(q_text, styles['Normal']))
        story.append(Spacer(1, 8))
        
        # Options for multiple choice (FIXED: checks type and key existence)
        if question.get('type') == 'multiple_choice' and 'options' in question:
            for i, option in enumerate(question['options']):
                # Process options for basic LaTeX rendering
                processed_option = process_latex_for_reportlab(option)
                # Ensure options are labeled (A), (B), etc.
                option_text = f"({chr(65+i)}) {processed_option}"
                story.append(Paragraph(option_text, styles['Normal']))
            story.append(Spacer(1, 12))
        else:
            # Space for answers (for short_answer or essay)
            story.append(Spacer(1, 40))
        
        question_num += 1
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_word_doc(paper_data):
    """Generate Word document version of the question paper with correct MCQ format"""
    doc = Document()
    
    # Title and Details
    title = doc.add_heading(paper_data['title'], 0)
    title.alignment = 1
    
    details_para = doc.add_paragraph()
    details_para.add_run('Subject: ').bold = True
    details_para.add_run(f"{paper_data['subject']}\n")
    details_para.add_run('Duration: ').bold = True
    details_para.add_run(f"{paper_data['duration']} minutes\n")
    details_para.add_run('Total Marks: ').bold = True
    details_para.add_run(f"{paper_data['total_marks']}\n")
    details_para.add_run('Difficulty: ').bold = True
    details_para.add_run(f"{paper_data['difficulty'].title()}")
    
    doc.add_paragraph()
    
    # Instructions
    instructions_para = doc.add_paragraph()
    instructions_para.add_run('Instructions:').bold = True
    doc.add_paragraph('1. Read all questions carefully before answering.')
    doc.add_paragraph('2. Answer all questions.')
    doc.add_paragraph('3. Write clearly and legibly.')
    doc.add_paragraph('4. Manage your time effectively.')
    
    doc.add_paragraph()
    
    # Questions
    questions = json.loads(paper_data['questions'])['questions']
    question_num = 1
    
    for question in questions:
        # Question text (NOTE: LaTeX appears as raw text here, as python-docx cannot render it simply)
        q_para = doc.add_paragraph()
        
        # We must strip the redundant dollar signs for Word, as Word doesn't handle ReportLab markup
        # The simplest way to handle the AI's overly aggressive dollar sign usage is to strip them for the Word doc if they contain simple content.
        # This is very difficult to do perfectly without external libraries, so we will only strip dollar signs if the content is trivial.
        
        q_text = question['question']
        
        def simple_strip_latex(text):
            """Remove dollar signs from text that appears to contain only simple numbers or words."""
            # Replace inline $...$ only if content is simple (e.g., $6$, $x$)
            return re.sub(r'\$(.*?)\$', lambda m: m.group(1) if re.fullmatch(r'[\w\s]+', m.group(1)) else m.group(0), text)
            
        
        q_para.add_run(f"Q{question_num}. {simple_strip_latex(q_text)} ({question['marks']} marks)").bold = True
        
        # Options for multiple choice (FIXED: checks type and key existence and formats options)
        if question.get('type') == 'multiple_choice' and 'options' in question:
            for i, option in enumerate(question['options']):
                # Ensure options are labeled (A), (B), etc. and strip simple $
                doc.add_paragraph(f"({chr(65+i)}) {simple_strip_latex(option)}")
        else:
            # Space for answers
            doc.add_paragraph()
            doc.add_paragraph()
        
        question_num += 1
    
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def create_file_response(file_buffer, filename, mimetype):
    """Create a Flask response for file download"""
    response = make_response(file_buffer.read())
    response.headers['Content-Type'] = mimetype
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response