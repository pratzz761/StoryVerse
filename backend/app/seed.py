"""Hand-written sample content. Never presented as generated output."""
DEMO_USER = "11111111-1111-4111-8111-111111111111"
PROFILES = [
    {"id": DEMO_USER, "display_name": "Alex Morgan", "bio": "Collecting little worlds and unfinished adventures.", "avatar_color": "purple"},
    {"id": "22222222-2222-4222-8222-222222222222", "display_name": "Maya Chen", "bio": "A soft spot for impossible places.", "avatar_color": "green"},
    {"id": "33333333-3333-4333-8333-333333333333", "display_name": "Jules Rivera", "bio": "One more chapter.", "avatar_color": "orange"},
]
# Curated canon for the existing three-chapter sample, not a model result.
FOREST_BIBLE = {
    "characters": [
        {"name": "Elara", "description": "A villager following a brass key bearing her mother's initials.",
         "relationships": ["Daughter of the woman whose voice is heard in the river.", "Guided by the fox."],
         "personality_traits": ["Curious", "Determined"],
         "visual_description": "A young traveler holding a small brass key; retain the same face and clothes across panels."},
        {"name": "The fox", "description": "An old talking fox who keeps lost things in a house inside a fallen tree.",
         "relationships": ["Guides Elara toward the river."], "personality_traits": ["Wry", "Patient"],
         "visual_description": "An old fox with spectacles balanced on his nose, beside shelves of lost objects."}],
    "important_events": ["Elara finds her mother's brass key in oak roots.", "The fox gives Elara an empty jar.",
        "The river stops when Elara lowers the jar into its water."],
    "unresolved_plotlines": ["Why is Elara's mother's voice coming from the other side of the river?"]}

SAMPLES = [
    ("The Forest That Remembers", "Fantasy", "forest", "Some places don't forget. Some are waiting for you to return.", [
        ("A name in the trees", "The forest had been calling her by a name she hadn't used in years.\n\nAt the edge of the village, Elara found a small brass key tangled in the roots of an oak. It was warm, as if someone had only just let go.\n\nShe turned it over. Her mother's initials were carved into its side. Somewhere beyond the trees, a bell rang once."),
        ("The keeper of small things", "Following the bell, Elara came to a house built inside a fallen tree. Its windows glowed amber. On the doorstep sat an old fox with a pair of spectacles balanced on his nose.\n\n\"You're late,\" he said. \"But then, your family always is.\"\n\nInside, every shelf held something lost: a single mitten, a sailor's compass, the sound of summer rain trapped in a jar."),
        ("What the river carried", "The fox placed an empty jar in Elara's hands. \"Before you open a door, you must remember what you left behind.\"\n\nAt the river, she heard her mother's laugh beneath the water. Not a memory. A voice, coming from the other side.\n\nElara knelt on the bank and held the jar beneath the surface. The river stopped moving.")]),
    ("Somewhere Beyond Tomorrow", "Sci-Fi", "space", "A lost signal. An unlikely crew. One last corner of the universe.", [
        ("The quiet frequency", "For thirty years, the observatory had listened to silence. Then, on an ordinary Tuesday, a signal arrived carrying the sound of a kettle boiling.\n\nNiko checked the coordinates twice. The transmission came from a star that no longer existed. At the end of the recording, a familiar voice said his name.")]),
    ("The Last Light in Kyoto", "Mystery", "city", "Every evening, one window lights up in an abandoned street.", [
        ("After the last train", "The last train had gone when Hana noticed the lantern. Across the tracks, in a station closed since 1986, someone was sweeping the platform.\n\nShe raised her camera. Through the viewfinder, the station was full of people. When she lowered it, there was only the woman with the broom.")]),
    ("Where the Ocean Ends", "Adventure", "ocean", "An old map leads two strangers to the edge of everything.", [
        ("A different kind of tide", "Every map in the shop ended at the same blue line. All except one.\n\nOn its far edge, in handwriting so small it looked like a crease, someone had written: keep sailing.\n\nOutside, the tide was pulling away from the harbor. The boats rose with it, as though the sea had become a hill.")]),
    ("Letters from the Moon", "Romance", "moon", "Two people, one impossible distance, and words that find their way.", [
        ("Return address unknown", "The envelope had no stamp. Only a small drawing of the moon, exactly as it had looked the night before.\n\nInside was a letter that began: I think we watched the same sunrise, just from different sides.\n\nSam left a reply on the windowsill. By morning, it was gone.")]),
    ("The City Beneath the Sand", "Fantasy", "desert", "The desert keeps its secrets. Until the wind changes.", [
        ("The wind's first word", "When the storm ended, a staircase stood in the middle of the dunes. It descended into the sand without a single grain on its steps.\n\nAri counted forty-seven stairs before finding the door. Behind it, a city breathed in the dark, and every clock was running backward.")]),
]
