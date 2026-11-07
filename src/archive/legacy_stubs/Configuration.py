import wikipedia
import requests
from typing import Dict, List, Optional
import logging
import random

logger = logging.getLogger(__name__)

class AIKnowledgeManager:
    def __init__(self):
        # Set up Wikipedia
        wikipedia.set_lang("en")
        
        # Common responses for different types of questions
        self.common_responses = {
            "greeting": [
                "Hello! How can I help you today?",
                "Hi there! What can I do for you?",
                "Hey! Nice to see you. How can I assist?",
                "Hello! Radhe here, ready to help.",
            ],
            "thanks": [
                "You're welcome!",
                "Happy to help!",
                "Anytime!",
                "My pleasure!",
            ],
            "goodbye": [
                "Goodbye! Have a great day!",
                "See you later!",
                "Take care!",
                "Bye! Don't hesitate to call me if you need anything.",
            ],
            "unknown": [
                "I'm not sure I understand. Could you rephrase that?",
                "I'm still learning. Could you try asking in a different way?",
                "I don't know how to help with that yet. Maybe try something else?",
                "That's beyond my capabilities at the moment. Is there something else I can help with?",
            ]
        }

    def answer_question(self, question: str) -> str:
        """Answer a general knowledge question"""
        question = question.lower()
        
        # Handle greetings
        if any(word in question for word in ["hello", "hi", "hey", "namaste"]):
            return random.choice(self.common_responses["greeting"])
            
        # Handle thanks
        if any(word in question for word in ["thank", "thanks", "appreciate"]):
            return random.choice(self.common_responses["thanks"])
            
        # Handle goodbye
        if any(word in question for word in ["goodbye", "bye", "see you"]):
            return random.choice(self.common_responses["goodbye"])
        
        # Try to answer with Wikipedia
        try:
            # Search for the topic
            search_results = wikipedia.search(question)
            if search_results:
                # Get the summary of the first result
                summary = wikipedia.summary(search_results[0], sentences=2)
                return f"According to Wikipedia: {summary}"
        except wikipedia.DisambiguationError as e:
            # Handle disambiguation pages
            options = e.options[:3]  # Get first 3 options
            return f"There are multiple meanings. Did you mean: {', '.join(options)}?"
        except wikipedia.PageError:
            # Page doesn't exist
            pass
        except Exception as e:
            logger.error(f"Error with Wikipedia: {e}")
        
        # If Wikipedia fails, try to give a generic response based on question type
        if any(word in question for word in ["what", "who", "when", "where", "why", "how"]):
            return self._generate_educated_guess(question)
        
        # Fallback to unknown response
        return random.choice(self.common_responses["unknown"])

    def wikipedia_search(self, topic: str) -> str:
        """Search for a topic on Wikipedia"""
        try:
            # Search for the topic
            search_results = wikipedia.search(topic)
            if not search_results:
                return f"I couldn't find anything about {topic} on Wikipedia."
            
            # Get the summary of the first result
            summary = wikipedia.summary(search_results[0], sentences=3)
            return f"Here's what I found about {topic} on Wikipedia: {summary}"
            
        except wikipedia.DisambiguationError as e:
            # Handle disambiguation pages
            options = e.options[:3]  # Get first 3 options
            return f"There are multiple meanings for {topic}. Did you mean: {', '.join(options)}?"
        except wikipedia.PageError:
            return f"I couldn't find a Wikipedia page for {topic}."
        except Exception as e:
            logger.error(f"Error with Wikipedia search: {e}")
            return f"Sorry, I encountered an error while searching for {topic}."

    def _generate_educated_guess(self, question: str) -> str:
        """Generate an educated guess for a question"""
        question = question.lower()
        
        # Simple pattern matching for common questions
        if "capital" in question:
            if "india" in question:
                return "The capital of India is New Delhi."
            elif "france" in question:
                return "The capital of France is Paris."
            elif "japan" in question:
                return "The capital of Japan is Tokyo."
            elif "usa" in question or "united states" in question:
                return "The capital of the United States is Washington, D.C."
        
        elif "population" in question:
            if "india" in question:
                return "The population of India is approximately 1.4 billion people."
            elif "world" in question:
                return "The world population is approximately 8 billion people."
            elif "china" in question:
                return "The population of China is approximately 1.4 billion people."
        
        elif "weather" in question:
            return "I can check the weather for you. Would you like me to do that?"
        
        elif "time" in question:
            return "I can tell you the current time. Would you like me to do that?"
        
        elif "date" in question:
            return "I can tell you today's date. Would you like me to do that?"
        
        # Default response for unknown questions
        return "I'm not sure about that. You might want to check a reliable source for accurate information."

    def translate_text(self, text: str, target_language: str) -> str:
        """Translate text to another language"""
        # This would typically use a translation API
        # For now, return a placeholder response
        supported_languages = {
            "hindi": "hi", "spanish": "es", "french": "fr", 
            "german": "de", "japanese": "ja", "chinese": "zh"
        }
        
        if target_language.lower() in supported_languages:
            return f"I would translate '{text}' to {target_language} here."
        else:
            return f"I don't support translation to {target_language} yet."

    def summarize_text(self, text: str) -> str:
        """Summarize a piece of text"""
        # This would typically use a summarization API or algorithm
        # For now, return a simple summary
        sentences = text.split('.')
        if len(sentences) > 3:
            summary = '.'.join(sentences[:2]) + '.'
            return f"Here's a summary: {summary}"
        else:
            return "The text is already quite short. Here it is: " + text

# Create a global instance for easy importing
ai_knowledge = AIKnowledgeManager()

# Example usage
if __name__ == "__main__":
    manager = AIKnowledgeManager()
    
    print(manager.answer_question("What is the capital of India?"))
    print(manager.wikipedia_search("Artificial Intelligence"))
    print(manager.answer_question("Hello Radhe!"))
    print(manager.answer_question("Thank you"))