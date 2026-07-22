"""Point d'entrée de MultiToolApp."""

from ui.app import MultiToolApp

def main() -> None:
    """Lance l'application."""
    app = MultiToolApp()
    app.mainloop()

if __name__ == "__main__":
    main()