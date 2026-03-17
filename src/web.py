# web.py
import requests
import wikipedia

class WebManager:
    """Handles web search and information retrieval"""
    
    def __init__(self):
        wikipedia.set_lang("en")

    def search_web(self, query: str) -> str:
        """
        Search the web for information using DuckDuckGo or Wikipedia.
        
        Args:
            query: Search query
            
        Returns:
            Search results summary
        """
        try:
            # Try Wikipedia first
            try:
                summary = wikipedia.summary(query, sentences=3)
                return summary
            except wikipedia.exceptions.DisambiguationError as e:
                # If disambiguated, take the first option
                option = e.options[0]
                summary = wikipedia.summary(option, sentences=2)
                return f"Did you mean {option}? {summary}"
            except wikipedia.exceptions.PageError:
                # Fallback to DuckDuckGo via API
                url = f"https://api.duckduckgo.com/?q={query}&format=json"
                response = requests.get(url, timeout=10)
                data = response.json()
                if 'Abstract' in data and data['Abstract']:
                    return data['Abstract']
                else:
                    return "No information found."
        except Exception as e:
            print(f"Error in search_web: {e}")
            return "Search failed."

    def get_daily_briefing(self) -> str:
        """
        Provide a daily briefing with news, weather, and reminders.
        
        Returns:
            Briefing string
        """
        # Placeholder implementation
        briefing = "Good morning! Here's your daily briefing:\n"
        briefing += "- Weather: Sunny with a high of 25°C.\n"
        briefing += "- Top news: [Insert news headline here]\n"
        briefing += "- Reminders: You have a meeting at 10 AM.\n"
        return briefing