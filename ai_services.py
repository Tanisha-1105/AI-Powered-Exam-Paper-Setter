import os
from dotenv import load_dotenv
import json
from google import genai
from google.genai import types
from google.genai.errors import APIError
import logging

# Configure logging: Level set to DEBUG for detailed error capture
logging.basicConfig(level=logging.DEBUG)

# Load environment variables from .env file
load_dotenv()
print("Is API Key loaded? (True/False):", os.getenv("GEMINI_API_KEY") is not None)
# Initialize Gemini client using the key from .env
try:
    # Ensure GEMINI_API_KEY is available in the environment
    if not os.getenv("GEMINI_API_KEY"):
        logging.warning("GEMINI_API_KEY environment variable is NOT set. AI functions will fail.")
        client = None
    else:
        # Client automatically uses the GEMINI_API_KEY from environment variables
        client = genai.Client()
        logging.info("✅ Gemini Client initialized successfully.")
except Exception as e:
    logging.error(f"⚠ Gemini Client initialization failed: {e}")
    client = None

MODEL_NAME = "gemini-2.5-flash"

def extract_clean_json(text):
    """
    Attempts to extract a clean JSON object from a string that might
    contain surrounding text, markdown, or other characters.
    """
    try:
        # Find the start of the JSON (first '{')
        start_index = text.find('{')
        # Find the end of the JSON (last '}')
        end_index = text.rfind('}')

        if start_index == -1 or end_index == -1:
            logging.error("Could not find start or end of JSON in response.")
            return None

        # Extract the substring between the braces (inclusive)
        json_string = text[start_index:end_index + 1]
        
        # Minimal cleanup for safety (removes common markdown wrappers)
        json_string = json_string.strip().lstrip('json').lstrip('').rstrip('').strip()
        
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON after extraction. Error: {e}")
        # Note: json_string variable is not defined outside of the try block, so use caution here.
        # logging.debug(f"Attempted JSON string that failed to parse: {json_string}") 
        return None
    except Exception as e:
        logging.error(f"General error during JSON extraction: {e}")
        return None

def generate_questions(subject, difficulty, question_counts):
    """
    Generate educational questions using Gemini API, respecting specific counts for each type.
    question_counts is expected to be a dict: {'one_word': N, 'short': M, 'essay': P}
    """
    if client is None:
        logging.error("Client is None. Returning fallback due to initialization failure.")
        # Fallback question updated to reflect the new expected type (one_word)
        return { "questions": [ { "type": "one_word", "question": f"Sample {subject} question (AI generation failed: Client not initialized)", "model_answer": "FALLBACK", "marks": 2, "explanation": "Fallback due to initialization error" } ] }

    total_questions = sum(question_counts.values())
    
    # Detailed instruction for the AI regarding the exact structure
    type_instructions = []
    

    if question_counts.get('one_word', 0) > 0:
        type_instructions.append(f"Generate exactly {question_counts['one_word']} one_word questions. The expected answer must be a single word and placed in the 'model_answer' field.")
    if question_counts.get('short', 0) > 0:
        type_instructions.append(f"Generate exactly {question_counts['short']} short_answer questions, providing model answers.")
    if question_counts.get('essay', 0) > 0:
        type_instructions.append(f"Generate exactly {question_counts['essay']} essay questions, providing marking criteria.")
    
    if not type_instructions:
        return { "questions": [] } # Should not happen based on frontend validation

    type_instructions_text = "\n".join(type_instructions)
    
    prompt = f"""
    Generate a total of {total_questions} educational questions for the subject "{subject}" with difficulty level "{difficulty}".
    
    *CRITICAL STRUCTURE INSTRUCTION:*
    {type_instructions_text}
    
   # In generate_questions function, update the prompt string:
   
    CRITICAL FORMATTING INSTRUCTION:* * For all mathematical and scientific notation, *DO NOT USE ANY LATEX COMMANDS* like \int, \sum, \frac, \mathbf, \in, or \mathbb. 
    * Use only *standard keyboard characters (ASCII/Unicode)* and spell out Greek letters.
    * Examples: Use 'p^n' for $p^n$, 'f(x) = x^2' for $f(x)=x^2$, and 'integral from 0 to infinity' instead of \int also f(v) instead of \mathbf(v).
    * Enclose all equations and variables in double parentheses ((...)) for easy reading.
    Return the response EXACTLY in a clean JSON format with this structure:
    {{
        "questions": [
            {{
                "type": "one_word", 
                "question": "Question text (must use $LaTeX$ for formulas)",
                "model_answer": "SINGLE_WORD_ANSWER", 
                "marks": 1,
                "explanation": "Brief explanation"
            }}, 
            {{
                "type": "short_answer",
                "question": "Question text (must use $LaTeX$ for formulas)",
                "model_answer": "Expected answer",
                "marks": 2,
                "marking_criteria": "Key points to look for"
            }},
            {{
                "type": "essay",
                "question": "Question text (must use $LaTeX$ for formulas)",
                "marks": 5,
                "marking_criteria": "Detailed marking rubric"
            }}
        ]
    }}
    Ensure questions are educationally appropriate and test understanding of {subject} concepts.
    """
    # --- END UPDATED PROMPT ---

    try:
        # Define JSON schema for structure enforcement
        response_schema = {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "question": {"type": "string"},
                            "marks": {"type": "integer"}
                        },
                        "required": ["type", "question", "marks"]
                    }
                }
            },
            "required": ["questions"]
        }

        # Passing system_instruction inside the config (correct syntax for the SDK)
        config = types.GenerateContentConfig(
            response_mime_type="application/json", 
            response_schema=response_schema,
            system_instruction="You are an expert exam question setter. Your primary goal is to return the content strictly as a clean JSON object. You MUST use standard LaTeX format enclosed in dollar signs for all math and scientific notation."
        )

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            config=config,
        )

        result_text = response.text
        
        logging.debug(f"Raw AI Response for Questions: {result_text[:500]}...")
        
        questions_data = extract_clean_json(result_text)
        
        if questions_data is None:
            raise Exception("AI response could not be parsed as final JSON structure.")

        return questions_data

    except APIError as e:
        # Fallback 2: API Error
        logging.error(f"⚠ Gemini API error (APIError): {e}")
        return { "questions": [ { "type": "one_word", "question": f"Sample {subject} question (AI generation failed: API Error)", "model_answer": "FALLBACK", "marks": 2, "explanation": "Fallback question due to API error" } ] }
    except Exception as e:
        # Fallback 3: General Error
        logging.error(f"⚠ General error in question generation (JSON or Unknown): {e}")
        return { "questions": [ { "type": "one_word", "question": f"Sample {subject} question (AI generation failed: General Error)", "model_answer": "FALLBACK", "marks": 2, "explanation": "Fallback question due to general error" } ] }


def grade_submission(questions, answers):
    """
    Grade a student's submission using Gemini API
    """
    if client is None:
        return {
            "total_score": 0, "max_score": sum(q.get("marks", 1) for q in questions),
            "question_scores": [], "overall_feedback": "Automatic grading failed: Client not initialized. Manual review required."
        }

    prompt = f"""
    Grade the following student answers based on the questions and marking criteria provided.
    Questions and Answers:
    {json.dumps({"questions": questions, "answers": answers}, indent=2)}
    Return the response EXACTLY in a clean JSON format:
    {{
        "total_score": number, "max_score": number,
        "question_scores": [
            {{ "question_number": 1, "score": number, "max_score": number, "feedback": "Detailed feedback" }}
        ],
        "overall_feedback": "General feedback on performance"
    }}
    Ensure your grading is fair, accurate, and the final output is only the requested JSON.
    """

    try:
        response_schema = {
            "type": "object",
            "properties": {
                "total_score": {"type": "number"}, "max_score": {"type": "number"},
                "question_scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_number": {"type": "integer"}, "score": {"type": "number"},
                            "max_score": {"type": "number"}, "feedback": {"type": "string"}
                        },
                        "required": ["question_number", "score", "max_score", "feedback"]
                    }
                }
            },
            "required": ["total_score", "max_score", "question_scores", "overall_feedback"]
        }

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            system_instruction="You are an expert educator. Grade student responses fairly and provide constructive feedback. Your only output must be the requested JSON."
        )

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            config=config,
        )

        content = response.text
        
        logging.debug(f"Raw AI Response for Grading: {content[:500]}...")

        grading_result = extract_clean_json(content)
        
        if grading_result is None:
            raise Exception("AI response could not be parsed as final JSON structure.")

        return grading_result

    except APIError as e:
        logging.error(f"⚠ Gemini API error (APIError): {e}")
        return {
            "total_score": 0, "max_score": sum(q.get("marks", 1) for q in questions),
            "question_scores": [], "overall_feedback": "Automatic grading failed due to API error. Manual review required."
        }
    except Exception as e:
        logging.error(f"⚠ General error in grading: {e}")
        return {
            "total_score": 0, "max_score": sum(q.get("marks", 1) for q in questions),
            "question_scores": [], "overall_feedback": "Automatic grading failed due to a general error. Manual review required."
        }