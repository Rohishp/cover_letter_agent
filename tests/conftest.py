from datetime import date

import pytest

from cv.facts import (
    CVFacts,
    Certifications,
    CertificationFact,
    Coursework,
    Education,
    EducationFact,
    Extras,
    LanguageFact,
    Languages,
    Meta,
    Personal,
    ProjectFact,
    Projects,
    SkillGroupFact,
    Skills,
    WorkExperience,
    WorkExperienceFact,
)


@pytest.fixture
def facts() -> CVFacts:
    """
    A small, self-contained fact base -- not the real cv_facts.yaml --
    covering every shape selection_rules.py and containment.py need to
    handle: an over-max experience entry, an "in progress" education
    entry, four projects, five skill groups, and coursework.
    """

    return CVFacts(
        meta=Meta(updated=date(2026, 1, 1), owner="Test Person"),
        personal=Personal(
            full_name="Test Person",
            location="Testville, Testland",
            email="test@example.com",
            phone="+1 555 0000",
            linkedin="https://www.linkedin.com/in/testperson",
            github="https://github.com/testperson",
            photo="exclude",
        ),
        languages=Languages(
            tier=1,
            entries=[LanguageFact(language="English", level="C1")],
        ),
        education=Education(
            tier=1,
            entries=[
                EducationFact(
                    degree="M.Sc. In Progress Degree",
                    institution="Test University",
                    city="Testville",
                    dates="01.2026 - present",
                    bullets=["In progress."],
                ),
                EducationFact(
                    degree="B.Sc. Computer Science",
                    institution="Old University",
                    city="Oldtown",
                    dates="2015 - 2018",
                    bullets=[
                        "Studied algorithms.",
                        "Studied databases.",
                        "Built a web app.",
                    ],
                ),
            ],
        ),
        work_experience=WorkExperience(
            tier=1,
            entries=[
                WorkExperienceFact(
                    position="Senior Thing Doer",
                    organisation="Acme Corp",
                    city="Metropolis",
                    dates="2020 - 2022",
                    bullets=[
                        "Did thing one with 42 widgets.",
                        "Did thing two.",
                        "Did thing three with 10x speedup.",
                        "Did thing four.",
                        "Did thing five.",
                        "Did thing six.",
                    ],
                ),
                WorkExperienceFact(
                    position="Junior Thing Doer",
                    organisation="Beta Inc",
                    city="Gotham",
                    dates="2018 - 2020",
                    bullets=[
                        "Helped with thing A.",
                        "Helped with thing B.",
                        "Helped with thing C.",
                    ],
                ),
            ],
        ),
        projects=Projects(
            tier=2,
            entries=[
                ProjectFact(
                    name="Widget Analyzer",
                    dates="2021",
                    status="complete",
                    tools="Python",
                    intro="Analyzes widgets.",
                    bullets=[
                        "Processed 1000 widgets per second.",
                        "Reduced errors by 20%.",
                    ],
                ),
                ProjectFact(
                    name="Gadget Tracker",
                    dates="2022",
                    status="complete",
                    tools="Python",
                    intro="Tracks gadgets.",
                    bullets=["Tracked gadgets in real time."],
                ),
                ProjectFact(
                    name="Doohickey Portal",
                    dates="2023",
                    status="complete",
                    tools="Python",
                    intro="Portal for doohickeys.",
                    bullets=["Built a portal."],
                ),
                ProjectFact(
                    name="Thingamajig App",
                    dates="2024",
                    status="complete",
                    tools="Python",
                    intro="App for thingamajigs.",
                    bullets=["Built an app."],
                ),
            ],
        ),
        certifications=Certifications(
            tier=1,
            entries=[
                CertificationFact(
                    name="Test Certified Professional",
                    issuer="Test Body",
                    issued="2022",
                ),
            ],
        ),
        skills=Skills(
            groups=[
                SkillGroupFact(name="Group A", items=["A1", "A2"]),
                SkillGroupFact(name="Group B", items=["B1"]),
                SkillGroupFact(name="Group C", items=["C1"]),
                SkillGroupFact(name="Group D", items=["D1"]),
                SkillGroupFact(name="Group E", items=["E1"]),
            ]
        ),
        coursework=Coursework(
            tier=3,
            include_when="embedded roles",
            exclude_when="pure web roles",
            render_as="bullet_list",
            items=["Studied embedded systems including RTOS and CAN."],
        ),
        extras=Extras(awards=[], volunteering=[]),
    )
