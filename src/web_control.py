# web_control.py
"""
Web helpers: open websites, search google/youtube, maps, weather, news.
- Uses webbrowser for safe open actions.
- URL-encodes query parts where necessary.
"""

import webbrowser
import logging
from urllib.parse import quote_plus

logger = logging.getLogger("Radhe_Web")
logger.setLevel(logging.INFO)

class WebController:
    def __init__(self):
        self.website_mappings = {
            "youtube": "https://youtube.com",
            "google": "https://google.com",
            "facebook": "https://facebook.com",
            "instagram": "https://instagram.com",
            "twitter": "https://twitter.com",
            "whatsapp": "https://web.whatsapp.com",
            "telegram": "https://web.telegram.org",
            "gmail": "https://mail.google.com",
            "outlook": "https://outlook.live.com",
            "netflix": "https://netflix.com",
            "github": "https://github.com",
            "stackoverflow": "https://stackoverflow.com",
            "amazon": "https://amazon.com",
            "flipkart": "https://flipkart.com",
            "wikipedia": "https://wikipedia.org",
        }

    def open_website(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            return "No website specified."
        key = name.lower()
        url = self.website_mappings.get(key)
        if not url:
            # try to form url
            if not key.startswith(("http://","https://")):
                url = "https://" + key.replace(" ", "")
            else:
                url = key
        try:
            webbrowser.open(url)
            return f"Opening {name}"
        except Exception as e:
            logger.exception("open_website error: %s", e)
            return f"Could not open {name}"

    def google_search(self, query: str) -> str:
        q = quote_plus(query or "")
        url = f"https://www.google.com/search?q={q}"
        webbrowser.open(url)
        return f"Searching Google for {query}"

    def youtube_search(self, query: str) -> str:
        q = quote_plus(query or "")
        url = f"https://www.youtube.com/results?search_query={q}"
        webbrowser.open(url)
        return f"Searching YouTube for {query}"

    def get_maps(self, location: str = "") -> str:
        if not location:
            webbrowser.open("https://www.google.com/maps")
            return "Opening Google Maps"
        webbrowser.open(f"https://www.google.com/maps/place/{quote_plus(location)}")
        return f"Showing maps for {location}"

    def get_weather(self, location: str = "") -> str:
        if location and location != "current":
            webbrowser.open(f"https://weather.com/weather/today/l/{quote_plus(location)}")
            return f"Showing weather for {location}"
        webbrowser.open("https://weather.com")
        return "Showing current weather"

    def get_news(self, category: str = "general") -> str:
        webbrowser.open("https://news.google.com")
        return "Opening news"

# global instance
web_controller = WebController()
