import webbrowser
from urllib.parse import quote


def google_search(query):

    url = "https://www.google.com/search?q=" + quote(query)

    webbrowser.open(url)

    return f"Searching Google for {query}."