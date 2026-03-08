import os
import logging
import asyncio
from typing import Optional
from backend.config import GROQ_API_KEY, GROQ_MODEL, GROQ_TIMEOUT
logger = logging.getLogger(__name__)

class GroqService: 
    def __init__(self, api_key: Optional[str] = None, model: str = GROQ_MODEL):
        self.api_key = api_key or GROQ_API_KEY
        self.model = model
        self.client = None
        self.is_available = False
        
    def init(self):
        if not self.api_key:
            logger.warning("[Groq] No API key configured - LLM features disabled")
            return
        
        try:
            from groq import Groq
            self.client = Groq(api_key=self.api_key)
            self.is_available = True
            logger.info(f"[Groq] Initialized with model: {self.model}")
        except ImportError:
            logger.warning("[Groq] groq package not installed - LLM features disabled")
        except Exception as e:
            logger.error(f"[Groq] Init error: {e}")
    
    async def expand_keywords(self, topic: str, language: str = "vi") -> str:
        """
        Expand a lecture topic into technical keywords for ASR priming
        
        Args:
            topic: Lecture topic (e.g., "Machine Learning cơ bản")
            language: Source language
            
        Returns:
            Comma-separated keywords string for WhisperX initial_prompt
        """
        if not self.is_available or not topic.strip():
            return ""
        
        lang_name = "Vietnamese" if language == "vi" else "English"
        
        prompt = f"""Given this lecture topic: "{topic}"
        Generate 15-20 technical keywords and phrases that are likely to appear in a {lang_name} lecture about this topic.
        Include: technical terms, abbreviations, proper nouns, and domain-specific vocabulary.
        For Vietnamese topics, include both Vietnamese terms and their English equivalents.
        Return ONLY the keywords as a comma-separated list. No explanations."""

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._chat, prompt)
            
            # Clean up: remove quotes, newlines, extra whitespace
            keywords = result.replace('"', '').replace('\n', ', ').strip()
            logger.info(f"[Groq] Keywords for '{topic[:30]}': {keywords[:100]}...")
            return keywords
            
        except Exception as e:
            logger.error(f"[Groq] expand_keywords error: {e}")
            return ""

    async def generate_context(self, topic: str, language: str = "vi") -> dict:
        """
        Generate both keywords AND a context paragraph for ASR priming.
        
        Returns:
            {"keywords": "comma,separated,list", "context": "2-3 sentence description"}
        """
        if not self.is_available or not topic.strip():
            return {"keywords": "", "context": ""}
        
        lang_name = "Vietnamese" if language == "vi" else "English"
        
        prompt = f"""Given this lecture topic: "{topic}"

Generate TWO things:

1. KEYWORDS: 15-20 technical keywords/phrases likely to appear in a {lang_name} lecture about this topic. Include technical terms, abbreviations, proper nouns, and domain-specific vocabulary. For Vietnamese topics, include both Vietnamese and English terms.

2. CONTEXT: A brief 2-3 sentence description of what this lecture covers. Write it as a natural paragraph that captures the key themes and terminology. This will be used as context for speech recognition.

Return in this EXACT format (no markdown, no extra text):
KEYWORDS: keyword1, keyword2, keyword3, ...
CONTEXT: Brief description paragraph here."""

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._chat, prompt)
            
            keywords = ""
            context = ""
            
            for line in result.strip().split('\n'):
                line = line.strip()
                if line.upper().startswith('KEYWORDS:'):
                    keywords = line[len('KEYWORDS:'):].strip().replace('"', '')
                elif line.upper().startswith('CONTEXT:'):
                    context = line[len('CONTEXT:'):].strip().replace('"', '')
            
            logger.info(f"[Groq] Context for '{topic[:30]}': keywords={len(keywords.split(','))} items, context={len(context)} chars")
            return {"keywords": keywords, "context": context}
            
        except Exception as e:
            logger.error(f"[Groq] generate_context error: {e}")
            return {"keywords": "", "context": ""}
    
    async def summarize_lecture(self, transcript: str, topic: str = "") -> str:
        """
        Generate a structured summary of the lecture transcript
        
        Args:
            transcript: Full transcript text
            topic: Optional lecture topic for context
            
        Returns:
            Markdown-formatted lecture summary
        """
        if not self.is_available or not transcript.strip():
            return ""
        
        topic_context = f'Topic: "{topic}"\n' if topic else ""
        
        # Truncate very long transcripts to fit context window
        max_chars = 25000  
        if len(transcript) > max_chars:
            transcript = transcript[:max_chars] + "\n... (truncated)"
        
        prompt = f"""{topic_context}Below is a lecture transcript. Create a concise, structured summary in Markdown format.

        Include:
        1. **Key Points** (3-5 bullet points)
        2. **Technical Terms** mentioned (with brief definitions if possible)
        3. **Action Items / Takeaways** (if any)

        Keep it concise and useful for a student reviewing notes.

        Transcript:
        ---
        {transcript}
        ---

        Summary:"""

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._chat, prompt)
            logger.info(f"[Groq] Summary generated ({len(result)} chars)")
            return result
            
        except Exception as e:
            logger.error(f"[Groq] summarize_lecture error: {e}")
            return ""
    
    def _chat(self, prompt: str) -> str:
        """Synchronous Groq chat completion"""
        if not self.client:
            return ""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", 
                "content": """
                    You are a highly skilled Academic Assistant specializing in lecture comprehension and educational synthesis. 
                    Your goal is to process lecture transcripts or notes and transform them into structured learning materials. 

                    ### Instructions:
                    1. **Core Analysis**: Identify the central thesis, key concepts, and supporting arguments.
                    2. **Terminology**: Extract specialized vocabulary and provide concise, context-specific definitions.
                    3. **Structured Summary**: Use a hierarchical format (Main Headings > Sub-points) to summarize the content.
                    4. **Active Learning**: Generate 3-5 high-level reflection questions to test the user's deep understanding.

                    ### Constraints:
                    - Maintain an objective, formal, and scholarly tone.
                    - If the input contains ambiguous points, highlight them for clarification.
                    - Use Markdown for clear visual hierarchy (bolding key terms, using bullet points).

                    ### Output Structure:
                    - ## Executive Summary
                    - ## Key Concepts & Definitions
                    - ## Detailed Breakdown
                    - ## Critical Thinking Questions
                """},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=1024,
            timeout=GROQ_TIMEOUT,
        )
        return response.choices[0].message.content.strip()