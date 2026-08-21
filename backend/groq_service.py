import os
import logging
import asyncio
import re
from typing import Optional
from backend.config import (
    GROQ_API_KEY,
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    GROQ_TIMEOUT,
)

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
            Comma-separated keywords string for the Faster-Whisper initial prompt
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
            
            # Clean up
            keywords = result.replace('"', '').replace('\n', ', ').strip()
            logger.info(f"[Groq] Keywords for '{topic[:30]}': {keywords[:100]}...")
            return keywords
            
        except Exception as e:
            logger.error(f"[Groq] expand_keywords error: {e}")
            return ""
    
    async def summarize_lecture(self, transcript: str, topic: str = "", language: str = "en") -> str:
        """
        Generate a structured summary of the lecture transcript
        
        Args:
            transcript: Full transcript text
            topic: Optional lecture topic for context
            language: Output language for the summary
            
        Returns:
            Markdown-formatted lecture summary
        """
        if not self.is_available or not transcript.strip():
            return ""
        
        topic_context = f'Topic: "{topic}"\n' if topic else ""
        language_name = {
            "en": "English",
            "vi": "Vietnamese",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "fr": "French",
            "de": "German",
            "es": "Spanish",
            "pt": "Portuguese",
            "ru": "Russian",
            "th": "Thai",
        }.get((language or "en").lower(), "English")
        
        # Truncate very long transcripts to fit context window
        max_chars = 25000  
        if len(transcript) > max_chars:
            transcript = transcript[:max_chars] + "\n... (truncated)"
        
        prompt = f"""{topic_context}Below is a lecture transcript. Create a concise, structured summary in Markdown format.
Write the summary in {language_name}.

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
            result = self._to_plain_text(result)
            logger.info(f"[Groq] Summary generated ({len(result)} chars)")
            return result
            
        except Exception as e:
            logger.error(f"[Groq] summarize_lecture error: {e}")
            return ""

    async def generate_context(self, topic: str, language: str = "vi") -> dict:
        """
        Generate both keyword hints and a short context paragraph for ASR priming.
        """
        if not self.is_available or not topic.strip():
            return {"keywords": "", "context": ""}

        lang_name = "Vietnamese" if language == "vi" else "English"
        prompt = f"""Given this lecture topic: \"{topic}\"

Generate:
1. A comma-separated list of 12-18 technical keywords likely to appear in a {lang_name} lecture.
2. A short context paragraph (2-3 sentences) that captures the likely subject matter and terminology.

Return the result in exactly this format:
KEYWORDS: keyword 1, keyword 2, keyword 3
CONTEXT: short paragraph here"""

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._chat, prompt)

            keywords = ""
            context = ""
            for line in result.splitlines():
                line = line.strip()
                if line.upper().startswith("KEYWORDS:"):
                    keywords = line.split(":", 1)[1].strip()
                elif line.upper().startswith("CONTEXT:"):
                    context = line.split(":", 1)[1].strip()

            if not keywords and result:
                keywords = result.replace('"', '').replace('\n', ', ').strip()

            logger.info(f"[Groq] Context generated for '{topic[:30]}'")
            return {"keywords": keywords, "context": context}
        except Exception as e:
            logger.error(f"[Groq] generate_context error: {e}")
            return {"keywords": "", "context": ""}

    async def answer_question(self, transcript: str, question: str, topic: str = "") -> str:
        """
        Answer a question using the current transcript as grounding context.
        """
        if not self.is_available or not transcript.strip() or not question.strip():
            return ""

        topic_context = f'Topic: "{topic}"\n' if topic else ""
        prompt = f"""{topic_context}Use only the transcript below to answer the question.
If the transcript does not contain enough information, say so clearly.

Question: {question}

Transcript:
---
{transcript[:25000]}
---

Answer:"""

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._chat, prompt)
            result = self._to_plain_text(result)
            logger.info(f"[Groq] Answered question for topic '{topic[:30]}'")
            return result
        except Exception as e:
            logger.error(f"[Groq] answer_question error: {e}")
            return ""
    
    @staticmethod
    def _to_plain_text(text: str) -> str:
        """Remove common Markdown syntax before returning text to the UI."""
        if not text:
            return ""

        cleaned = text
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
        cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
        cleaned = re.sub(r"_(.*?)_", r"\1", cleaned)
        cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"^[ \t]*[-*+][ \t]+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^[ \t]*>+[ \t]?", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _chat(self, prompt: str) -> str:
        """Synchronous Groq chat completion"""
        if not self.client:
            return ""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise academic assistant. Follow the requested format exactly and return plain text unless Markdown is explicitly requested.",
                },
                {"role": "user", "content": prompt}
            ],
            temperature=GROQ_TEMPERATURE,
            max_tokens=GROQ_MAX_TOKENS,
            timeout=GROQ_TIMEOUT,
        )
        
        return response.choices[0].message.content.strip()
