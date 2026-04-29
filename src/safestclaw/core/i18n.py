"""
SafestClaw Internationalization - Deterministic multilingual command understanding.

Maps command keywords and natural-language phrases in multiple languages
to the same English intent names used by the parser.  No AI or ML required:
this is pure dictionary lookup + the same fuzzy-matching the parser already does.

Supported languages (add more by extending LANGUAGE_PACK):
  es - Spanish       fr - French        de - German
  pt - Portuguese    it - Italian       nl - Dutch
  ru - Russian       zh - Chinese       ja - Japanese
  ko - Korean        ar - Arabic        tr - Turkish
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Type alias for a single language pack.
# Each language pack maps intent names to:
#   "keywords"  – list of translated trigger words
#   "phrases"   – list of translated natural-language phrase variations
# ---------------------------------------------------------------------------
IntentTranslation = dict[str, list[str]]
LanguagePack = dict[str, IntentTranslation]

# ---------------------------------------------------------------------------
# Master dictionary: lang-code -> { intent -> { keywords, phrases } }
# ---------------------------------------------------------------------------
LANGUAGE_PACK: dict[str, LanguagePack] = {
    # ------------------------------------------------------------------
    # Spanish
    # ------------------------------------------------------------------
    "es": {
        "reminder": {
            "keywords": [
                "recordar", "recordatorio", "recordarme", "alerta",
                "avisar", "aviso", "notificar",
            ],
            "phrases": [
                "no me dejes olvidar",
                "avísame",
                "recuérdame",
                "necesito recordar",
                "ponme una alerta",
                "hazme acordar",
                "no olvides",
                "acuérdame de",
            ],
        },
        "weather": {
            "keywords": [
                "clima", "tiempo", "temperatura", "pronóstico",
                "lluvia", "soleado", "frío", "calor",
            ],
            "phrases": [
                "cómo está el clima",
                "va a llover",
                "hace frío",
                "hace calor",
                "qué temperatura hace",
                "necesito paraguas",
                "necesito chaqueta",
                "pronóstico del tiempo",
            ],
        },
        "summarize": {
            "keywords": [
                "resumir", "resumen", "resumé", "sintetizar", "condensar",
            ],
            "phrases": [
                "hazme un resumen",
                "resúmeme esto",
                "dame los puntos clave",
                "en resumen",
                "versión corta",
            ],
        },
        "crawl": {
            "keywords": [
                "rastrear", "extraer", "obtener", "recopilar", "enlaces",
            ],
            "phrases": [
                "qué enlaces hay en",
                "muéstrame los enlaces de",
                "escanear sitio web",
                "obtener enlaces de",
            ],
        },
        "email": {
            "keywords": [
                "correo", "email", "bandeja", "mensaje", "enviar correo",
            ],
            "phrases": [
                "hay correo nuevo",
                "nuevos mensajes",
                "revisar correo",
                "escribir correo",
                "enviar mensaje a",
            ],
        },
        "calendar": {
            "keywords": [
                "calendario", "agenda", "reunión", "evento", "cita",
            ],
            "phrases": [
                "qué tengo hoy",
                "estoy ocupado",
                "tengo algo pendiente",
                "tiempo libre",
                "agendar reunión",
                "eventos de hoy",
            ],
        },
        "news": {
            "keywords": [
                "noticias", "titulares", "novedades", "prensa",
            ],
            "phrases": [
                "qué hay de nuevo",
                "últimas noticias",
                "qué está pasando",
                "noticias del día",
                "noticias recientes",
            ],
        },
        "briefing": {
            "keywords": [
                "resumen diario", "informe", "actualización",
            ],
            "phrases": [
                "ponme al día",
                "qué pasó hoy",
                "resumen del día",
                "resumen matutino",
                "empezar mi día",
            ],
        },
        "help": {
            "keywords": [
                "ayuda", "comandos", "opciones",
            ],
            "phrases": [
                "qué puedes hacer",
                "cómo funciona esto",
                "mostrar opciones",
                "lista de funciones",
                "menú",
            ],
        },
        "shell": {
            "keywords": [
                "ejecutar", "comando", "terminal",
            ],
            "phrases": [
                "ejecutar comando",
                "correr esto",
            ],
        },
        "smarthome": {
            "keywords": [
                "luz", "luces", "lámpara", "encender", "apagar", "atenuar",
            ],
            "phrases": [
                "enciende las luces",
                "apaga las luces",
                "ponlo más brillante",
                "ponlo más oscuro",
            ],
        },
        "files": {
            "keywords": [
                "archivo", "archivos", "carpeta", "buscar", "encontrar",
            ],
            "phrases": [
                "listar archivos en",
                "buscar archivos",
                "encontrar archivos",
            ],
        },
        "blog": {
            "keywords": [
                "blog", "publicar", "entrada", "artículo",
            ],
            "phrases": [
                "escribir blog",
                "publicar entrada",
                "crear artículo",
                "nuevo blog",
            ],
        },
        "analyze": {
            "keywords": [
                "analizar", "sentimiento", "análisis",
            ],
            "phrases": [
                "analizar sentimiento",
                "extraer palabras clave",
            ],
        },
        "document": {
            "keywords": [
                "documento", "leer archivo",
            ],
            "phrases": [
                "leer documento",
                "abrir archivo",
            ],
        },
        "notify": {
            "keywords": [
                "notificación", "avisar", "alerta de escritorio",
            ],
            "phrases": [
                "enviar notificación",
                "notifícame que",
            ],
        },
        "vision": {
            "keywords": [
                "detectar", "objetos", "imagen", "identificar",
            ],
            "phrases": [
                "detectar objetos en",
                "qué hay en esta imagen",
            ],
        },
        "ocr": {
            "keywords": [
                "ocr", "escanear", "extraer texto",
            ],
            "phrases": [
                "escanear texto de",
                "extraer texto de",
            ],
        },
        "entities": {
            "keywords": [
                "entidades", "personas", "lugares", "organizaciones",
            ],
            "phrases": [
                "extraer entidades de",
                "encontrar personas en",
            ],
        },
    },
    # ------------------------------------------------------------------
    # French
    # ------------------------------------------------------------------
    "fr": {
        "reminder": {
            "keywords": [
                "rappeler", "rappel", "souvenir", "alerte", "avertir",
                "pense-bête",
            ],
            "phrases": [
                "ne me laisse pas oublier",
                "rappelle-moi",
                "fais-moi penser",
                "n'oublie pas de",
                "mets un rappel",
                "préviens-moi",
            ],
        },
        "weather": {
            "keywords": [
                "météo", "température", "prévisions", "pluie",
                "ensoleillé", "froid", "chaud",
            ],
            "phrases": [
                "quel temps fait-il",
                "est-ce qu'il pleut",
                "fait-il froid",
                "fait-il chaud",
                "ai-je besoin d'un parapluie",
                "prévisions météo",
            ],
        },
        "summarize": {
            "keywords": [
                "résumer", "résumé", "synthèse", "condenser",
            ],
            "phrases": [
                "fais-moi un résumé",
                "résume-moi ça",
                "les points clés",
                "en bref",
                "version courte",
            ],
        },
        "crawl": {
            "keywords": [
                "explorer", "extraire", "récupérer", "liens",
            ],
            "phrases": [
                "quels liens sur",
                "montre-moi les liens de",
                "scanner le site",
            ],
        },
        "email": {
            "keywords": [
                "courriel", "courrier", "boîte de réception", "message",
                "envoyer email",
            ],
            "phrases": [
                "nouveaux courriels",
                "vérifier mes emails",
                "écrire un email",
                "envoyer un message à",
            ],
        },
        "calendar": {
            "keywords": [
                "calendrier", "agenda", "réunion", "événement",
                "rendez-vous",
            ],
            "phrases": [
                "qu'est-ce que j'ai aujourd'hui",
                "suis-je occupé",
                "planifier une réunion",
                "événements du jour",
            ],
        },
        "news": {
            "keywords": [
                "nouvelles", "actualités", "informations", "presse",
                "titres",
            ],
            "phrases": [
                "quoi de neuf",
                "dernières nouvelles",
                "que se passe-t-il",
                "actualités du jour",
            ],
        },
        "briefing": {
            "keywords": [
                "briefing", "résumé quotidien", "mise à jour",
            ],
            "phrases": [
                "mets-moi au courant",
                "résumé du matin",
                "commencer ma journée",
            ],
        },
        "help": {
            "keywords": [
                "aide", "commandes", "options",
            ],
            "phrases": [
                "que peux-tu faire",
                "comment ça marche",
                "montre les options",
            ],
        },
        "shell": {
            "keywords": [
                "exécuter", "commande", "terminal", "lancer",
            ],
            "phrases": [
                "exécuter la commande",
                "lance ça",
            ],
        },
        "smarthome": {
            "keywords": [
                "lumière", "lumières", "lampe", "allumer", "éteindre",
                "tamiser",
            ],
            "phrases": [
                "allume les lumières",
                "éteins les lumières",
                "plus lumineux",
                "plus sombre",
            ],
        },
        "files": {
            "keywords": [
                "fichier", "fichiers", "dossier", "chercher", "trouver",
            ],
            "phrases": [
                "lister les fichiers dans",
                "chercher des fichiers",
                "trouver des fichiers",
            ],
        },
        "blog": {
            "keywords": [
                "blog", "publier", "article", "billet",
            ],
            "phrases": [
                "écrire un blog",
                "publier un article",
                "nouveau blog",
            ],
        },
        "analyze": {
            "keywords": [
                "analyser", "sentiment", "analyse",
            ],
            "phrases": [
                "analyser le sentiment",
                "extraire les mots-clés",
            ],
        },
        "document": {
            "keywords": [
                "document", "lire fichier",
            ],
            "phrases": [
                "lire le document",
                "ouvrir le fichier",
            ],
        },
        "notify": {
            "keywords": [
                "notification", "avertir", "alerte bureau",
            ],
            "phrases": [
                "envoyer une notification",
                "préviens-moi que",
            ],
        },
        "vision": {
            "keywords": [
                "détecter", "objets", "image", "identifier",
            ],
            "phrases": [
                "détecter les objets dans",
                "qu'y a-t-il dans cette image",
            ],
        },
        "ocr": {
            "keywords": [
                "ocr", "numériser", "extraire texte",
            ],
            "phrases": [
                "numériser le texte de",
                "extraire le texte de",
            ],
        },
        "entities": {
            "keywords": [
                "entités", "personnes", "lieux", "organisations",
            ],
            "phrases": [
                "extraire les entités de",
                "trouver les personnes dans",
            ],
        },
    },
    # ------------------------------------------------------------------
    # German
    # ------------------------------------------------------------------
    "de": {
        "reminder": {
            "keywords": [
                "erinnern", "erinnerung", "wecker", "alarm",
                "benachrichtigen", "merken",
            ],
            "phrases": [
                "erinnere mich",
                "lass mich nicht vergessen",
                "vergiss nicht",
                "merk dir",
                "erinnerung setzen",
                "sag mir bescheid",
            ],
        },
        "weather": {
            "keywords": [
                "wetter", "temperatur", "vorhersage", "regen",
                "sonnig", "kalt", "warm",
            ],
            "phrases": [
                "wie ist das wetter",
                "regnet es",
                "ist es kalt",
                "ist es warm",
                "brauche ich einen regenschirm",
                "wettervorhersage",
            ],
        },
        "summarize": {
            "keywords": [
                "zusammenfassen", "zusammenfassung", "kurzfassung",
            ],
            "phrases": [
                "fass mir das zusammen",
                "zusammenfassung davon",
                "die wichtigsten punkte",
                "kurzversion",
            ],
        },
        "crawl": {
            "keywords": [
                "durchsuchen", "extrahieren", "abrufen", "links",
            ],
            "phrases": [
                "welche links gibt es auf",
                "zeig mir die links von",
                "webseite scannen",
            ],
        },
        "email": {
            "keywords": [
                "email", "e-mail", "posteingang", "nachricht",
                "senden",
            ],
            "phrases": [
                "neue e-mails",
                "e-mails prüfen",
                "email schreiben",
                "nachricht senden an",
            ],
        },
        "calendar": {
            "keywords": [
                "kalender", "terminplan", "besprechung", "termin",
                "ereignis",
            ],
            "phrases": [
                "was habe ich heute",
                "bin ich beschäftigt",
                "besprechung planen",
                "termine heute",
                "habe ich etwas vor",
            ],
        },
        "news": {
            "keywords": [
                "nachrichten", "schlagzeilen", "neuigkeiten", "presse",
            ],
            "phrases": [
                "was gibt es neues",
                "neueste nachrichten",
                "was passiert gerade",
                "aktuelle nachrichten",
            ],
        },
        "briefing": {
            "keywords": [
                "briefing", "tagesbericht", "zusammenfassung",
                "aktualisierung",
            ],
            "phrases": [
                "bring mich auf den neuesten stand",
                "morgenbriefing",
                "tagesübersicht",
            ],
        },
        "help": {
            "keywords": [
                "hilfe", "befehle", "optionen",
            ],
            "phrases": [
                "was kannst du",
                "wie funktioniert das",
                "optionen anzeigen",
            ],
        },
        "shell": {
            "keywords": [
                "ausführen", "befehl", "terminal",
            ],
            "phrases": [
                "befehl ausführen",
                "führe das aus",
            ],
        },
        "smarthome": {
            "keywords": [
                "licht", "lichter", "lampe", "einschalten",
                "ausschalten", "dimmen",
            ],
            "phrases": [
                "licht einschalten",
                "licht ausschalten",
                "heller machen",
                "dunkler machen",
            ],
        },
        "files": {
            "keywords": [
                "datei", "dateien", "ordner", "suchen", "finden",
            ],
            "phrases": [
                "dateien auflisten in",
                "dateien suchen",
                "dateien finden",
            ],
        },
        "blog": {
            "keywords": [
                "blog", "veröffentlichen", "beitrag", "artikel",
            ],
            "phrases": [
                "blog schreiben",
                "beitrag veröffentlichen",
                "neuer blog",
            ],
        },
        "analyze": {
            "keywords": [
                "analysieren", "stimmung", "analyse",
            ],
            "phrases": [
                "stimmung analysieren",
                "schlüsselwörter extrahieren",
            ],
        },
        "document": {
            "keywords": [
                "dokument", "datei lesen",
            ],
            "phrases": [
                "dokument lesen",
                "datei öffnen",
            ],
        },
        "notify": {
            "keywords": [
                "benachrichtigung", "warnung", "desktop-warnung",
            ],
            "phrases": [
                "benachrichtigung senden",
                "benachrichtige mich",
            ],
        },
        "vision": {
            "keywords": [
                "erkennen", "objekte", "bild", "identifizieren",
            ],
            "phrases": [
                "objekte erkennen in",
                "was ist auf diesem bild",
            ],
        },
        "ocr": {
            "keywords": [
                "ocr", "scannen", "text extrahieren",
            ],
            "phrases": [
                "text scannen von",
                "text extrahieren aus",
            ],
        },
        "entities": {
            "keywords": [
                "entitäten", "personen", "orte", "organisationen",
            ],
            "phrases": [
                "entitäten extrahieren aus",
                "personen finden in",
            ],
        },
    },
    # ------------------------------------------------------------------
    # Portuguese
    # ------------------------------------------------------------------
    "pt": {
        "reminder": {
            "keywords": [
                "lembrar", "lembrete", "lembrar-me", "alerta",
                "avisar", "aviso",
            ],
            "phrases": [
                "não me deixes esquecer",
                "avisa-me",
                "lembra-me",
                "preciso lembrar",
                "coloca um alerta",
                "não esqueças de",
            ],
        },
        "weather": {
            "keywords": [
                "clima", "tempo", "temperatura", "previsão",
                "chuva", "ensolarado", "frio", "calor",
            ],
            "phrases": [
                "como está o tempo",
                "vai chover",
                "está frio",
                "está calor",
                "preciso de guarda-chuva",
                "previsão do tempo",
            ],
        },
        "summarize": {
            "keywords": [
                "resumir", "resumo", "sintetizar", "condensar",
            ],
            "phrases": [
                "faz-me um resumo",
                "resume isto",
                "pontos principais",
                "em resumo",
                "versão curta",
            ],
        },
        "crawl": {
            "keywords": [
                "rastrear", "extrair", "obter", "recolher", "links",
            ],
            "phrases": [
                "que links existem em",
                "mostra-me os links de",
                "escanear site",
            ],
        },
        "email": {
            "keywords": [
                "correio", "email", "caixa de entrada", "mensagem",
                "enviar email",
            ],
            "phrases": [
                "há correio novo",
                "novas mensagens",
                "verificar email",
                "escrever email",
            ],
        },
        "calendar": {
            "keywords": [
                "calendário", "agenda", "reunião", "evento",
                "compromisso",
            ],
            "phrases": [
                "o que tenho hoje",
                "estou ocupado",
                "agendar reunião",
                "eventos de hoje",
            ],
        },
        "news": {
            "keywords": [
                "notícias", "manchetes", "novidades", "imprensa",
            ],
            "phrases": [
                "o que há de novo",
                "últimas notícias",
                "o que está acontecendo",
                "notícias do dia",
            ],
        },
        "briefing": {
            "keywords": [
                "resumo diário", "relatório", "atualização",
            ],
            "phrases": [
                "põe-me a par",
                "resumo da manhã",
                "começar o meu dia",
            ],
        },
        "help": {
            "keywords": ["ajuda", "comandos", "opções"],
            "phrases": [
                "o que podes fazer",
                "como funciona isto",
                "mostrar opções",
            ],
        },
        "shell": {
            "keywords": ["executar", "comando", "terminal"],
            "phrases": ["executar comando", "correr isto"],
        },
        "smarthome": {
            "keywords": [
                "luz", "luzes", "lâmpada", "ligar", "desligar", "diminuir",
            ],
            "phrases": [
                "ligar as luzes",
                "desligar as luzes",
                "mais brilho",
                "menos brilho",
            ],
        },
        "files": {
            "keywords": ["arquivo", "arquivos", "pasta", "procurar", "encontrar"],
            "phrases": ["listar arquivos em", "procurar arquivos"],
        },
        "blog": {
            "keywords": ["blog", "publicar", "postagem", "artigo"],
            "phrases": ["escrever blog", "publicar artigo", "novo blog"],
        },
        "analyze": {
            "keywords": ["analisar", "sentimento", "análise"],
            "phrases": ["analisar sentimento", "extrair palavras-chave"],
        },
        "document": {
            "keywords": ["documento", "ler arquivo"],
            "phrases": ["ler documento", "abrir arquivo"],
        },
        "notify": {
            "keywords": ["notificação", "avisar"],
            "phrases": ["enviar notificação", "notifica-me que"],
        },
        "vision": {
            "keywords": ["detectar", "objetos", "imagem", "identificar"],
            "phrases": ["detectar objetos em", "o que está nesta imagem"],
        },
        "ocr": {
            "keywords": ["ocr", "digitalizar", "extrair texto"],
            "phrases": ["digitalizar texto de", "extrair texto de"],
        },
        "entities": {
            "keywords": ["entidades", "pessoas", "lugares", "organizações"],
            "phrases": ["extrair entidades de", "encontrar pessoas em"],
        },
    },
    # ------------------------------------------------------------------
    # Italian
    # ------------------------------------------------------------------
    "it": {
        "reminder": {
            "keywords": [
                "ricordare", "promemoria", "ricordami", "avviso",
                "avvisare", "allarme",
            ],
            "phrases": [
                "non farmi dimenticare",
                "ricordami di",
                "avvisami",
                "non dimenticare di",
                "imposta un promemoria",
            ],
        },
        "weather": {
            "keywords": [
                "meteo", "temperatura", "previsioni", "pioggia",
                "soleggiato", "freddo", "caldo",
            ],
            "phrases": [
                "che tempo fa",
                "pioverà",
                "fa freddo",
                "fa caldo",
                "ho bisogno dell'ombrello",
                "previsioni meteo",
            ],
        },
        "summarize": {
            "keywords": [
                "riassumere", "riassunto", "sintesi", "condensare",
            ],
            "phrases": [
                "fammi un riassunto",
                "riassumimi questo",
                "i punti chiave",
                "in breve",
                "versione breve",
            ],
        },
        "crawl": {
            "keywords": ["esplorare", "estrarre", "ottenere", "link"],
            "phrases": [
                "quali link ci sono su",
                "mostrami i link di",
                "scansionare il sito",
            ],
        },
        "email": {
            "keywords": [
                "email", "posta", "casella", "messaggio", "inviare email",
            ],
            "phrases": [
                "c'è posta nuova",
                "nuovi messaggi",
                "controlla la posta",
                "scrivi un'email",
            ],
        },
        "calendar": {
            "keywords": [
                "calendario", "agenda", "riunione", "evento",
                "appuntamento",
            ],
            "phrases": [
                "cosa ho oggi",
                "sono occupato",
                "programmare una riunione",
                "eventi di oggi",
            ],
        },
        "news": {
            "keywords": ["notizie", "titoli", "novità", "stampa"],
            "phrases": [
                "cosa c'è di nuovo",
                "ultime notizie",
                "cosa sta succedendo",
                "notizie del giorno",
            ],
        },
        "briefing": {
            "keywords": ["riepilogo giornaliero", "rapporto", "aggiornamento"],
            "phrases": [
                "aggiornami",
                "riepilogo del mattino",
                "iniziare la giornata",
            ],
        },
        "help": {
            "keywords": ["aiuto", "comandi", "opzioni"],
            "phrases": [
                "cosa puoi fare",
                "come funziona",
                "mostra le opzioni",
            ],
        },
        "shell": {
            "keywords": ["eseguire", "comando", "terminale"],
            "phrases": ["eseguire il comando", "esegui questo"],
        },
        "smarthome": {
            "keywords": [
                "luce", "luci", "lampada", "accendere", "spegnere",
                "attenuare",
            ],
            "phrases": [
                "accendi le luci",
                "spegni le luci",
                "più luminoso",
                "più scuro",
            ],
        },
        "files": {
            "keywords": ["file", "cartella", "cercare", "trovare"],
            "phrases": ["elencare i file in", "cercare file", "trovare file"],
        },
        "blog": {
            "keywords": ["blog", "pubblicare", "articolo", "post"],
            "phrases": ["scrivere un blog", "pubblicare articolo", "nuovo blog"],
        },
        "analyze": {
            "keywords": ["analizzare", "sentimento", "analisi"],
            "phrases": ["analizzare il sentimento", "estrarre parole chiave"],
        },
        "document": {
            "keywords": ["documento", "leggere file"],
            "phrases": ["leggere il documento", "aprire il file"],
        },
        "notify": {
            "keywords": ["notifica", "avvisare", "avviso desktop"],
            "phrases": ["inviare notifica", "avvisami che"],
        },
        "vision": {
            "keywords": ["rilevare", "oggetti", "immagine", "identificare"],
            "phrases": ["rilevare oggetti in", "cosa c'è in questa immagine"],
        },
        "ocr": {
            "keywords": ["ocr", "scansionare", "estrarre testo"],
            "phrases": ["scansionare testo da", "estrarre testo da"],
        },
        "entities": {
            "keywords": ["entità", "persone", "luoghi", "organizzazioni"],
            "phrases": ["estrarre entità da", "trovare persone in"],
        },
    },
    # ------------------------------------------------------------------
    # Dutch
    # ------------------------------------------------------------------
    "nl": {
        "reminder": {
            "keywords": [
                "herinneren", "herinnering", "waarschuwing",
                "melden", "onthouden",
            ],
            "phrases": [
                "laat me niet vergeten",
                "herinner me eraan",
                "vergeet niet",
                "herinnering instellen",
            ],
        },
        "weather": {
            "keywords": [
                "weer", "temperatuur", "voorspelling", "regen",
                "zonnig", "koud", "warm",
            ],
            "phrases": [
                "hoe is het weer",
                "gaat het regenen",
                "is het koud",
                "is het warm",
                "heb ik een paraplu nodig",
                "weersvoorspelling",
            ],
        },
        "summarize": {
            "keywords": ["samenvatten", "samenvatting", "beknopt"],
            "phrases": [
                "geef me een samenvatting",
                "vat dit samen",
                "de kernpunten",
                "korte versie",
            ],
        },
        "crawl": {
            "keywords": ["doorzoeken", "extraheren", "ophalen", "links"],
            "phrases": ["welke links staan op", "toon de links van"],
        },
        "email": {
            "keywords": ["email", "postvak", "bericht", "sturen"],
            "phrases": [
                "nieuwe e-mails",
                "e-mail controleren",
                "email schrijven",
            ],
        },
        "calendar": {
            "keywords": ["kalender", "agenda", "vergadering", "afspraak"],
            "phrases": [
                "wat heb ik vandaag",
                "ben ik bezet",
                "vergadering plannen",
            ],
        },
        "news": {
            "keywords": ["nieuws", "koppen", "nieuwigheden", "pers"],
            "phrases": [
                "wat is er nieuw",
                "laatste nieuws",
                "wat gebeurt er",
            ],
        },
        "briefing": {
            "keywords": ["dagelijks overzicht", "update"],
            "phrases": ["breng me op de hoogte", "ochtendbriefing"],
        },
        "help": {
            "keywords": ["hulp", "commando's", "opties"],
            "phrases": ["wat kun je", "hoe werkt dit", "toon opties"],
        },
        "shell": {
            "keywords": ["uitvoeren", "opdracht", "terminal"],
            "phrases": ["opdracht uitvoeren", "voer dit uit"],
        },
        "smarthome": {
            "keywords": ["licht", "lichten", "lamp", "aanzetten", "uitzetten", "dimmen"],
            "phrases": ["licht aanzetten", "licht uitzetten", "helderder", "donkerder"],
        },
        "files": {
            "keywords": ["bestand", "bestanden", "map", "zoeken", "vinden"],
            "phrases": ["bestanden weergeven in", "bestanden zoeken"],
        },
        "blog": {
            "keywords": ["blog", "publiceren", "bericht", "artikel"],
            "phrases": ["blog schrijven", "artikel publiceren", "nieuw blog"],
        },
        "analyze": {
            "keywords": ["analyseren", "sentiment", "analyse"],
            "phrases": ["sentiment analyseren", "trefwoorden extraheren"],
        },
        "document": {
            "keywords": ["document", "bestand lezen"],
            "phrases": ["document lezen", "bestand openen"],
        },
        "notify": {
            "keywords": ["melding", "waarschuwen"],
            "phrases": ["melding sturen", "meld me dat"],
        },
        "vision": {
            "keywords": ["detecteren", "objecten", "afbeelding", "identificeren"],
            "phrases": ["objecten detecteren in", "wat staat er op deze afbeelding"],
        },
        "ocr": {
            "keywords": ["ocr", "scannen", "tekst extraheren"],
            "phrases": ["tekst scannen van", "tekst extraheren uit"],
        },
        "entities": {
            "keywords": ["entiteiten", "personen", "plaatsen", "organisaties"],
            "phrases": ["entiteiten extraheren uit", "personen vinden in"],
        },
    },
    # ------------------------------------------------------------------
    # Russian
    # ------------------------------------------------------------------
    "ru": {
        "reminder": {
            "keywords": [
                "напомнить", "напоминание", "запомнить", "оповещение",
                "уведомить",
            ],
            "phrases": [
                "не дай мне забыть",
                "напомни мне",
                "запомни это",
                "поставь напоминание",
                "не забудь",
            ],
        },
        "weather": {
            "keywords": [
                "погода", "температура", "прогноз", "дождь",
                "солнечно", "холодно", "жарко",
            ],
            "phrases": [
                "какая погода",
                "будет дождь",
                "холодно ли",
                "жарко ли",
                "нужен ли зонт",
                "прогноз погоды",
            ],
        },
        "summarize": {
            "keywords": ["резюмировать", "резюме", "краткое содержание", "сократить"],
            "phrases": [
                "сделай резюме",
                "подведи итог",
                "основные моменты",
                "кратко",
                "короткая версия",
            ],
        },
        "crawl": {
            "keywords": ["сканировать", "извлечь", "получить", "ссылки"],
            "phrases": ["какие ссылки на", "покажи ссылки с", "просканировать сайт"],
        },
        "email": {
            "keywords": ["почта", "электронная почта", "входящие", "сообщение", "отправить"],
            "phrases": [
                "новая почта",
                "новые сообщения",
                "проверить почту",
                "написать письмо",
            ],
        },
        "calendar": {
            "keywords": ["календарь", "расписание", "встреча", "событие"],
            "phrases": [
                "что у меня сегодня",
                "я занят",
                "запланировать встречу",
                "события на сегодня",
            ],
        },
        "news": {
            "keywords": ["новости", "заголовки", "новинки", "пресса"],
            "phrases": [
                "что нового",
                "последние новости",
                "что происходит",
                "новости дня",
            ],
        },
        "briefing": {
            "keywords": ["сводка", "отчёт", "обновление"],
            "phrases": ["введи в курс дела", "утренняя сводка", "начать мой день"],
        },
        "help": {
            "keywords": ["помощь", "команды", "параметры"],
            "phrases": ["что ты умеешь", "как это работает", "показать параметры"],
        },
        "shell": {
            "keywords": ["выполнить", "команда", "терминал"],
            "phrases": ["выполнить команду", "запусти это"],
        },
        "smarthome": {
            "keywords": ["свет", "лампа", "включить", "выключить", "приглушить"],
            "phrases": ["включи свет", "выключи свет", "ярче", "темнее"],
        },
        "files": {
            "keywords": ["файл", "файлы", "папка", "искать", "найти"],
            "phrases": ["показать файлы в", "искать файлы"],
        },
        "blog": {
            "keywords": ["блог", "опубликовать", "запись", "статья"],
            "phrases": ["написать блог", "опубликовать статью", "новый блог"],
        },
        "analyze": {
            "keywords": ["анализировать", "настроение", "анализ"],
            "phrases": ["анализировать настроение", "извлечь ключевые слова"],
        },
        "document": {
            "keywords": ["документ", "читать файл"],
            "phrases": ["прочитать документ", "открыть файл"],
        },
        "notify": {
            "keywords": ["уведомление", "оповестить"],
            "phrases": ["отправить уведомление", "уведоми меня"],
        },
        "vision": {
            "keywords": ["обнаружить", "объекты", "изображение", "определить"],
            "phrases": ["обнаружить объекты на", "что на этом изображении"],
        },
        "ocr": {
            "keywords": ["ocr", "сканировать", "извлечь текст"],
            "phrases": ["сканировать текст с", "извлечь текст из"],
        },
        "entities": {
            "keywords": ["сущности", "люди", "места", "организации"],
            "phrases": ["извлечь сущности из", "найти людей в"],
        },
    },
    # ------------------------------------------------------------------
    # Chinese (Simplified)
    # ------------------------------------------------------------------
    "zh": {
        "reminder": {
            "keywords": ["提醒", "备忘", "记住", "闹钟", "通知"],
            "phrases": [
                "别让我忘了",
                "提醒我",
                "记住这个",
                "设置提醒",
                "不要忘记",
            ],
        },
        "weather": {
            "keywords": ["天气", "温度", "预报", "下雨", "晴天", "冷", "热"],
            "phrases": [
                "天气怎么样",
                "会下雨吗",
                "冷不冷",
                "热不热",
                "需要带伞吗",
                "天气预报",
            ],
        },
        "summarize": {
            "keywords": ["总结", "摘要", "概括", "精简"],
            "phrases": [
                "给我一个总结",
                "总结一下",
                "主要内容",
                "简短版本",
            ],
        },
        "crawl": {
            "keywords": ["爬取", "抓取", "提取", "获取", "链接"],
            "phrases": ["有哪些链接在", "显示链接", "扫描网站"],
        },
        "email": {
            "keywords": ["邮件", "电子邮件", "收件箱", "消息", "发送邮件"],
            "phrases": ["有新邮件吗", "新消息", "检查邮件", "写邮件"],
        },
        "calendar": {
            "keywords": ["日历", "日程", "会议", "事件", "约会"],
            "phrases": ["今天有什么", "我忙吗", "安排会议", "今天的事件"],
        },
        "news": {
            "keywords": ["新闻", "头条", "最新消息", "资讯"],
            "phrases": ["有什么新的", "最新新闻", "发生了什么", "今天的新闻"],
        },
        "briefing": {
            "keywords": ["每日简报", "报告", "更新"],
            "phrases": ["给我更新", "早间简报", "开始我的一天"],
        },
        "help": {
            "keywords": ["帮助", "命令", "选项"],
            "phrases": ["你能做什么", "这怎么用", "显示选项"],
        },
        "shell": {
            "keywords": ["运行", "执行", "命令", "终端"],
            "phrases": ["运行命令", "执行这个"],
        },
        "smarthome": {
            "keywords": ["灯", "灯光", "打开", "关闭", "调暗"],
            "phrases": ["开灯", "关灯", "调亮", "调暗"],
        },
        "files": {
            "keywords": ["文件", "文件夹", "搜索", "查找"],
            "phrases": ["列出文件", "搜索文件", "查找文件"],
        },
        "blog": {
            "keywords": ["博客", "发布", "文章", "帖子"],
            "phrases": ["写博客", "发布文章", "新博客"],
        },
        "analyze": {
            "keywords": ["分析", "情感", "情绪"],
            "phrases": ["分析情感", "提取关键词"],
        },
        "document": {
            "keywords": ["文档", "读取文件"],
            "phrases": ["读取文档", "打开文件"],
        },
        "notify": {
            "keywords": ["通知", "提醒"],
            "phrases": ["发送通知", "通知我"],
        },
        "vision": {
            "keywords": ["检测", "物体", "图片", "识别"],
            "phrases": ["检测物体", "这张图片里有什么"],
        },
        "ocr": {
            "keywords": ["ocr", "扫描", "提取文字"],
            "phrases": ["扫描文字", "从图片提取文字"],
        },
        "entities": {
            "keywords": ["实体", "人物", "地点", "组织"],
            "phrases": ["提取实体", "查找人物"],
        },
    },
    # ------------------------------------------------------------------
    # Japanese
    # ------------------------------------------------------------------
    "ja": {
        "reminder": {
            "keywords": ["リマインダー", "思い出す", "覚える", "通知", "アラーム"],
            "phrases": [
                "忘れないように",
                "思い出させて",
                "リマインダーを設定",
                "忘れないで",
            ],
        },
        "weather": {
            "keywords": ["天気", "気温", "予報", "雨", "晴れ", "寒い", "暑い"],
            "phrases": [
                "天気はどう",
                "雨が降りますか",
                "寒いですか",
                "暑いですか",
                "傘が必要",
                "天気予報",
            ],
        },
        "summarize": {
            "keywords": ["要約", "まとめ", "概要", "簡潔"],
            "phrases": [
                "要約して",
                "まとめて",
                "主なポイント",
                "短い版",
            ],
        },
        "crawl": {
            "keywords": ["クロール", "抽出", "取得", "リンク"],
            "phrases": ["リンクを表示", "サイトをスキャン"],
        },
        "email": {
            "keywords": ["メール", "受信箱", "メッセージ", "送信"],
            "phrases": ["新しいメール", "メールを確認", "メールを書く"],
        },
        "calendar": {
            "keywords": ["カレンダー", "予定", "会議", "イベント"],
            "phrases": ["今日の予定", "忙しいですか", "会議を予約", "今日のイベント"],
        },
        "news": {
            "keywords": ["ニュース", "見出し", "最新情報"],
            "phrases": ["何か新しい", "最新ニュース", "何が起きている", "今日のニュース"],
        },
        "briefing": {
            "keywords": ["ブリーフィング", "日報", "更新情報"],
            "phrases": ["最新情報を教えて", "朝のブリーフィング", "一日を始める"],
        },
        "help": {
            "keywords": ["ヘルプ", "コマンド", "オプション", "助けて"],
            "phrases": ["何ができる", "使い方", "オプションを表示"],
        },
        "shell": {
            "keywords": ["実行", "コマンド", "ターミナル"],
            "phrases": ["コマンドを実行", "これを実行して"],
        },
        "smarthome": {
            "keywords": ["ライト", "電気", "つける", "消す", "暗く"],
            "phrases": ["電気をつけて", "電気を消して", "明るく", "暗くして"],
        },
        "files": {
            "keywords": ["ファイル", "フォルダ", "検索", "探す"],
            "phrases": ["ファイルを一覧", "ファイルを検索"],
        },
        "blog": {
            "keywords": ["ブログ", "公開", "記事", "投稿"],
            "phrases": ["ブログを書く", "記事を公開", "新しいブログ"],
        },
        "analyze": {
            "keywords": ["分析", "感情", "センチメント"],
            "phrases": ["感情を分析", "キーワードを抽出"],
        },
        "document": {
            "keywords": ["ドキュメント", "ファイルを読む"],
            "phrases": ["ドキュメントを読む", "ファイルを開く"],
        },
        "notify": {
            "keywords": ["通知", "お知らせ"],
            "phrases": ["通知を送信", "知らせて"],
        },
        "vision": {
            "keywords": ["検出", "オブジェクト", "画像", "識別"],
            "phrases": ["オブジェクトを検出", "この画像に何がある"],
        },
        "ocr": {
            "keywords": ["ocr", "スキャン", "テキスト抽出"],
            "phrases": ["テキストをスキャン", "テキストを抽出"],
        },
        "entities": {
            "keywords": ["エンティティ", "人物", "場所", "組織"],
            "phrases": ["エンティティを抽出", "人物を見つける"],
        },
    },
    # ------------------------------------------------------------------
    # Korean
    # ------------------------------------------------------------------
    "ko": {
        "reminder": {
            "keywords": ["알림", "리마인더", "기억", "알려줘", "경고"],
            "phrases": [
                "잊지 않게 해줘",
                "알려줘",
                "리마인더 설정",
                "잊지 마",
            ],
        },
        "weather": {
            "keywords": ["날씨", "기온", "예보", "비", "맑음", "추워", "더워"],
            "phrases": [
                "날씨 어때",
                "비 올까",
                "추워",
                "더워",
                "우산 필요해",
                "날씨 예보",
            ],
        },
        "summarize": {
            "keywords": ["요약", "정리", "개요", "간략"],
            "phrases": ["요약해줘", "정리해줘", "주요 내용", "짧은 버전"],
        },
        "crawl": {
            "keywords": ["크롤링", "추출", "가져오기", "링크"],
            "phrases": ["링크 보여줘", "사이트 스캔"],
        },
        "email": {
            "keywords": ["이메일", "메일", "받은편지함", "메시지", "보내기"],
            "phrases": ["새 메일", "메일 확인", "메일 쓰기"],
        },
        "calendar": {
            "keywords": ["달력", "일정", "회의", "이벤트", "약속"],
            "phrases": ["오늘 일정", "바쁜가요", "회의 예약", "오늘 이벤트"],
        },
        "news": {
            "keywords": ["뉴스", "헤드라인", "최신", "소식"],
            "phrases": ["새로운 소식", "최신 뉴스", "무슨 일이야", "오늘 뉴스"],
        },
        "briefing": {
            "keywords": ["브리핑", "일일 보고", "업데이트"],
            "phrases": ["최신 소식 알려줘", "아침 브리핑", "하루 시작"],
        },
        "help": {
            "keywords": ["도움말", "명령어", "옵션"],
            "phrases": ["뭘 할 수 있어", "어떻게 써", "옵션 보여줘"],
        },
        "shell": {
            "keywords": ["실행", "명령", "터미널"],
            "phrases": ["명령 실행", "이거 실행해"],
        },
        "smarthome": {
            "keywords": ["조명", "불", "켜기", "끄기", "어둡게"],
            "phrases": ["불 켜줘", "불 꺼줘", "밝게", "어둡게"],
        },
        "files": {
            "keywords": ["파일", "폴더", "검색", "찾기"],
            "phrases": ["파일 목록", "파일 검색"],
        },
        "blog": {
            "keywords": ["블로그", "게시", "글", "포스트"],
            "phrases": ["블로그 쓰기", "글 게시", "새 블로그"],
        },
        "analyze": {
            "keywords": ["분석", "감정", "센티먼트"],
            "phrases": ["감정 분석", "키워드 추출"],
        },
        "document": {
            "keywords": ["문서", "파일 읽기"],
            "phrases": ["문서 읽기", "파일 열기"],
        },
        "notify": {
            "keywords": ["알림", "통지"],
            "phrases": ["알림 보내기", "알려줘"],
        },
        "vision": {
            "keywords": ["감지", "객체", "이미지", "식별"],
            "phrases": ["객체 감지", "이 이미지에 뭐가 있어"],
        },
        "ocr": {
            "keywords": ["ocr", "스캔", "텍스트 추출"],
            "phrases": ["텍스트 스캔", "텍스트 추출"],
        },
        "entities": {
            "keywords": ["엔티티", "인물", "장소", "조직"],
            "phrases": ["엔티티 추출", "인물 찾기"],
        },
    },
    # ------------------------------------------------------------------
    # Arabic
    # ------------------------------------------------------------------
    "ar": {
        "reminder": {
            "keywords": ["تذكير", "تنبيه", "ذكرني", "إنذار", "تنبيه"],
            "phrases": [
                "لا تدعني أنسى",
                "ذكرني",
                "لا تنسَ",
                "ضع تذكيراً",
            ],
        },
        "weather": {
            "keywords": ["طقس", "حرارة", "توقعات", "مطر", "مشمس", "بارد", "حار"],
            "phrases": [
                "كيف الطقس",
                "هل ستمطر",
                "هل الجو بارد",
                "هل الجو حار",
                "هل أحتاج مظلة",
                "توقعات الطقس",
            ],
        },
        "summarize": {
            "keywords": ["تلخيص", "ملخص", "اختصار"],
            "phrases": ["لخص لي", "أعطني ملخصاً", "النقاط الرئيسية", "باختصار"],
        },
        "crawl": {
            "keywords": ["زحف", "استخراج", "جلب", "روابط"],
            "phrases": ["ما الروابط في", "أظهر الروابط من", "فحص الموقع"],
        },
        "email": {
            "keywords": ["بريد", "إيميل", "صندوق الوارد", "رسالة", "إرسال"],
            "phrases": ["بريد جديد", "رسائل جديدة", "تحقق من البريد", "اكتب بريداً"],
        },
        "calendar": {
            "keywords": ["تقويم", "جدول", "اجتماع", "حدث", "موعد"],
            "phrases": ["ماذا لدي اليوم", "هل أنا مشغول", "جدولة اجتماع", "أحداث اليوم"],
        },
        "news": {
            "keywords": ["أخبار", "عناوين", "مستجدات", "صحافة"],
            "phrases": ["ما الجديد", "آخر الأخبار", "ماذا يحدث", "أخبار اليوم"],
        },
        "briefing": {
            "keywords": ["إحاطة", "تقرير يومي", "تحديث"],
            "phrases": ["أطلعني", "إحاطة الصباح", "ابدأ يومي"],
        },
        "help": {
            "keywords": ["مساعدة", "أوامر", "خيارات"],
            "phrases": ["ماذا تستطيع أن تفعل", "كيف يعمل هذا", "أظهر الخيارات"],
        },
        "shell": {
            "keywords": ["تنفيذ", "أمر", "طرفية"],
            "phrases": ["تنفيذ الأمر", "شغل هذا"],
        },
        "smarthome": {
            "keywords": ["ضوء", "أضواء", "مصباح", "تشغيل", "إطفاء", "خفت"],
            "phrases": ["شغل الأضواء", "أطفئ الأضواء", "أكثر سطوعاً", "أكثر عتمة"],
        },
        "files": {
            "keywords": ["ملف", "ملفات", "مجلد", "بحث", "إيجاد"],
            "phrases": ["قائمة الملفات في", "البحث عن ملفات"],
        },
        "blog": {
            "keywords": ["مدونة", "نشر", "مقال", "تدوينة"],
            "phrases": ["كتابة مدونة", "نشر مقال", "مدونة جديدة"],
        },
        "analyze": {
            "keywords": ["تحليل", "مشاعر", "تحليل"],
            "phrases": ["تحليل المشاعر", "استخراج الكلمات المفتاحية"],
        },
        "document": {
            "keywords": ["مستند", "قراءة ملف"],
            "phrases": ["قراءة المستند", "فتح الملف"],
        },
        "notify": {
            "keywords": ["إشعار", "تنبيه"],
            "phrases": ["إرسال إشعار", "أشعرني أن"],
        },
        "vision": {
            "keywords": ["كشف", "أجسام", "صورة", "تعرف"],
            "phrases": ["كشف الأجسام في", "ماذا في هذه الصورة"],
        },
        "ocr": {
            "keywords": ["ocr", "مسح", "استخراج نص"],
            "phrases": ["مسح النص من", "استخراج النص من"],
        },
        "entities": {
            "keywords": ["كيانات", "أشخاص", "أماكن", "منظمات"],
            "phrases": ["استخراج الكيانات من", "إيجاد الأشخاص في"],
        },
    },
    # ------------------------------------------------------------------
    # Turkish
    # ------------------------------------------------------------------
    "tr": {
        "reminder": {
            "keywords": [
                "hatırlat", "hatırlatma", "hatırla", "uyarı",
                "bildir", "alarm",
            ],
            "phrases": [
                "unutmama izin verme",
                "bana hatırlat",
                "unutma",
                "hatırlatma kur",
            ],
        },
        "weather": {
            "keywords": [
                "hava", "sıcaklık", "tahmin", "yağmur",
                "güneşli", "soğuk", "sıcak",
            ],
            "phrases": [
                "hava nasıl",
                "yağmur yağacak mı",
                "soğuk mu",
                "sıcak mı",
                "şemsiye lazım mı",
                "hava tahmini",
            ],
        },
        "summarize": {
            "keywords": ["özetle", "özet", "kısalt"],
            "phrases": ["bana bir özet ver", "bunu özetle", "ana noktalar", "kısa versiyon"],
        },
        "crawl": {
            "keywords": ["tara", "çıkar", "getir", "bağlantılar"],
            "phrases": ["hangi bağlantılar var", "bağlantıları göster", "siteyi tara"],
        },
        "email": {
            "keywords": ["e-posta", "posta", "gelen kutusu", "mesaj", "gönder"],
            "phrases": ["yeni e-posta", "yeni mesajlar", "e-postayı kontrol et", "e-posta yaz"],
        },
        "calendar": {
            "keywords": ["takvim", "program", "toplantı", "etkinlik", "randevu"],
            "phrases": ["bugün ne var", "meşgul müyüm", "toplantı planla", "bugünkü etkinlikler"],
        },
        "news": {
            "keywords": ["haberler", "başlıklar", "yenilikler", "basın"],
            "phrases": ["ne var ne yok", "son haberler", "neler oluyor", "günün haberleri"],
        },
        "briefing": {
            "keywords": ["brifing", "günlük rapor", "güncelleme"],
            "phrases": ["beni bilgilendir", "sabah brifing", "günüme başla"],
        },
        "help": {
            "keywords": ["yardım", "komutlar", "seçenekler"],
            "phrases": ["ne yapabilirsin", "bu nasıl çalışır", "seçenekleri göster"],
        },
        "shell": {
            "keywords": ["çalıştır", "komut", "terminal"],
            "phrases": ["komutu çalıştır", "bunu çalıştır"],
        },
        "smarthome": {
            "keywords": ["ışık", "ışıklar", "lamba", "aç", "kapat", "kıs"],
            "phrases": ["ışıkları aç", "ışıkları kapat", "daha parlak", "daha karanlık"],
        },
        "files": {
            "keywords": ["dosya", "dosyalar", "klasör", "ara", "bul"],
            "phrases": ["dosyaları listele", "dosya ara"],
        },
        "blog": {
            "keywords": ["blog", "yayınla", "yazı", "makale"],
            "phrases": ["blog yaz", "makale yayınla", "yeni blog"],
        },
        "analyze": {
            "keywords": ["analiz", "duygu", "çözümleme"],
            "phrases": ["duygu analizi", "anahtar kelimeleri çıkar"],
        },
        "document": {
            "keywords": ["belge", "dosya oku"],
            "phrases": ["belgeyi oku", "dosyayı aç"],
        },
        "notify": {
            "keywords": ["bildirim", "uyar"],
            "phrases": ["bildirim gönder", "bana bildir"],
        },
        "vision": {
            "keywords": ["algıla", "nesneler", "görüntü", "tanımla"],
            "phrases": ["nesneleri algıla", "bu görüntüde ne var"],
        },
        "ocr": {
            "keywords": ["ocr", "tara", "metin çıkar"],
            "phrases": ["metni tara", "metni çıkar"],
        },
        "entities": {
            "keywords": ["varlıklar", "kişiler", "yerler", "kuruluşlar"],
            "phrases": ["varlıkları çıkar", "kişileri bul"],
        },
    },
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

# Human-readable language names for display
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish (Español)",
    "fr": "French (Français)",
    "de": "German (Deutsch)",
    "pt": "Portuguese (Português)",
    "it": "Italian (Italiano)",
    "nl": "Dutch (Nederlands)",
    "ru": "Russian (Русский)",
    "zh": "Chinese (中文)",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "ar": "Arabic (العربية)",
    "tr": "Turkish (Türkçe)",
}


def get_supported_languages() -> list[str]:
    """Return list of supported language codes (including 'en')."""
    return ["en"] + sorted(LANGUAGE_PACK.keys())


def get_language_name(code: str) -> str:
    """Return human-readable name for a language code."""
    return LANGUAGE_NAMES.get(code, code)


def get_language_pack(lang: str) -> LanguagePack | None:
    """Return the full language pack for *lang*, or None if unsupported."""
    return LANGUAGE_PACK.get(lang)


def get_keywords_for_intent(lang: str, intent: str) -> list[str]:
    """Return translated keywords for a single intent in a language."""
    pack = LANGUAGE_PACK.get(lang)
    if not pack:
        return []
    entry = pack.get(intent)
    if not entry:
        return []
    return entry.get("keywords", [])


def get_phrases_for_intent(lang: str, intent: str) -> list[str]:
    """Return translated phrase variations for a single intent in a language."""
    pack = LANGUAGE_PACK.get(lang)
    if not pack:
        return []
    entry = pack.get(intent)
    if not entry:
        return []
    return entry.get("phrases", [])
