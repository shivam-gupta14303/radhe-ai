import webbrowser
import logging
import socket
from urllib.parse import quote_plus

logger = logging.getLogger("Radhe_Web")
logger.setLevel(logging.INFO)


class WebController:

    def __init__(self):
        self.website_mappings = {
            "youtube":      "https://youtube.com",
            "google":       "https://google.com",
            "facebook":     "https://facebook.com",
            "instagram":    "https://instagram.com",
            "twitter":      "https://twitter.com",
            "x":            "https://twitter.com",
            "whatsapp":     "https://web.whatsapp.com",
            "telegram":     "https://web.telegram.org",
            "gmail":        "https://mail.google.com",
            "outlook":      "https://outlook.live.com",
            "netflix":      "https://netflix.com",
            "github":       "https://github.com",
            "stackoverflow":"https://stackoverflow.com",
            "amazon":       "https://amazon.in",
            "flipkart":     "https://flipkart.com",
            "wikipedia":    "https://wikipedia.org",
            "linkedin":     "https://linkedin.com",
            "reddit":       "https://reddit.com",
            "hotstar":      "https://hotstar.com",
            "spotify":      "https://open.spotify.com",
        }

    # ==================================================================
    # CORE OPEN
    # ==================================================================

    def open_website(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            return "No website specified."

        key = name.lower()
        url = self.website_mappings.get(key)

        if not url:
            # ✅ FIXED URL HANDLING
            if name.startswith(("http://", "https://")):
                url = name
            else:
                cleaned = name.replace(" ", "")
                if "." not in cleaned:
                    cleaned += ".com"
                url = "https://" + cleaned

        try:
            webbrowser.open(url)
            return f"Opening {name}."
        except Exception as e:
            logger.exception("open_website error: %s", e)
            return f"Could not open {name}."

    # ==================================================================
    # SEARCH
    # ==================================================================

    def google_search(self, query: str) -> str:
        if not query:
            return "What should I search for?"
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
        return f"Searching Google for: {query}."

    def youtube_search(self, query: str) -> str:
        if not query:
            return "What should I search on YouTube?"
        webbrowser.open(
            f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        )
        return f"Searching YouTube for: {query}."

    def news_search(self, topic: str = "") -> str:
        if topic:
            webbrowser.open(
                f"https://news.google.com/search?q={quote_plus(topic)}"
            )
            return f"Opening news about {topic}."
        webbrowser.open("https://news.google.com")
        return "Opening Google News."

    # ==================================================================
    # MAPS
    # ==================================================================

    def get_maps(self, location: str = "", origin: str = "", dest: str = "") -> str:
        if origin and dest:
            url = (
                f"https://www.google.com/maps/dir/"
                f"{quote_plus(origin)}/{quote_plus(dest)}"
            )
            webbrowser.open(url)
            return f"Getting directions from {origin} to {dest}."

        if location:
            webbrowser.open(
                f"https://www.google.com/maps/place/{quote_plus(location)}"
            )
            return f"Showing maps for {location}."

        webbrowser.open("https://www.google.com/maps")
        return "Opening Google Maps."

    # ==================================================================
    # WEATHER
    # ==================================================================

    def get_weather(self, location: str = "") -> str:
        if location and location.lower() != "current":
            webbrowser.open(
                f"https://weather.com/weather/today/l/{quote_plus(location)}"
            )
            return f"Showing weather for {location}."
        webbrowser.open("https://weather.com")
        return "Opening current weather."

    # ==================================================================
    # CONNECTIVITY
    # ==================================================================

    def is_online(self) -> bool:
        try:
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
                ("8.8.8.8", 53)
            )
            return True
        except Exception:
            return False

    def check_internet(self) -> str:
        if self.is_online():
            return "Yes, you're connected to the internet."
        return "No internet connection detected right now."


# GLOBAL INSTANCE
web_controller = WebController()