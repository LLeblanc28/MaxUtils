"""Glisser-déposer de fichiers, en dépendance facultative.

tkinterdnd2 embarque des binaires natifs (tkdnd) qui peuvent manquer ou ne pas
se charger selon la plateforme et le mode d'empaquetage. Toutes les fonctions
d'ici échouent donc silencieusement en retournant False : l'application reste
pleinement utilisable via les boutons « Ajouter des fichiers », le glisser-
déposer n'étant qu'un raccourci.
"""


def enable_dnd(root) -> bool:
    """Initialise tkdnd sur la fenêtre racine, une fois pour toute l'application.

    Returns:
        True si le glisser-déposer est disponible, False sinon.
    """
    try:
        from tkinterdnd2 import TkinterDnD

        root.TkdndVersion = TkinterDnD.require(root)
    except Exception:
        return False
    return True


def parse_drop_paths(widget, data: str) -> list[str]:
    """Découpe la chaîne déposée par tkdnd en une liste de chemins.

    tkdnd renvoie une liste au format Tcl, où les chemins contenant des
    espaces sont entourés d'accolades : « {C:/mes documents/a.pdf} b.pdf ».
    L'interpréteur Tcl est le seul à savoir la découper sans se tromper, d'où
    l'usage de `splitlist` plutôt qu'un `split()` naïf.
    """
    try:
        return [str(p) for p in widget.tk.splitlist(data)]
    except Exception:
        return [data] if data else []


def register_drop_target(widget, callback) -> bool:
    """Fait d'un widget une cible de dépôt de fichiers.

    Args:
        widget: widget qui recevra le dépôt.
        callback: reçoit la liste des chemins déposés.

    Returns:
        True si l'enregistrement a réussi, False si le glisser-déposer est
        indisponible — auquel cas le widget reste utilisable normalement.
    """
    try:
        from tkinterdnd2 import DND_FILES

        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>",
                        lambda event: callback(parse_drop_paths(widget, event.data)))
    except Exception:
        return False
    return True
