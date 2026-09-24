"""Phase 9: The 16-question acceptance test set from the assignment, Section 8."""

from subagents.schemas import EmployeeProfile

TEST_SET = [
    {
        "id": 1,
        "question": "How many earned leaves do I get a year, and how many can I carry forward?",
        "profile": EmployeeProfile(),
        "expected_departments": ["hr"],
        "key_points": ["18 days", "1.5 per month", "carry forward up to a 30-day balance"],
    },
    {
        "id": 2,
        "question": "My VPN keeps disconnecting. What should I do?",
        "profile": EmployeeProfile(),
        "expected_departments": ["it"],
        "key_points": [
            "update client", "switch network", "reset profile", "P3 ticket",
            "1 business day",
        ],
    },
    {
        "id": 3,
        "question": "What is my daily meal limit on a business trip?",
        "profile": EmployeeProfile(grade="G4"),
        "expected_departments": ["finance"],
        "key_points": ["INR 1,500 per day", "all cities"],
    },
    {
        "id": 4,
        "question": "How long do I have to submit an expense claim?",
        "profile": EmployeeProfile(),
        "expected_departments": ["finance"],
        "key_points": ["within 30 days", "rejected after 60 days"],
    },
    {
        "id": 5,
        "question": "What is my hotel limit per night in Nashik?",
        "profile": EmployeeProfile(grade="G2", current_city="Nashik"),
        "expected_departments": ["finance"],
        "key_points": ["Nashik is non-metro", "75% of INR 4,000", "INR 3,000"],
    },
    {
        "id": 6,
        "question": "I lost my laptop at the airport. What now?",
        "profile": EmployeeProfile(),
        "expected_departments": ["it"],
        "key_points": [
            "P1 ticket within 24 hours", "police complaint copy", "remote wipe",
            "25% of book value if negligent",
        ],
    },
    {
        "id": 7,
        "question": "Can I paste customer data into ChatGPT to summarise it?",
        "profile": EmployeeProfile(),
        "expected_departments": ["it"],
        "key_points": [
            "customer data is Confidential", "never in public or free tools",
            "Kestrel Copilot", "ChatGPT Enterprise workspace",
        ],
    },
    {
        "id": 8,
        "question": "I join next Monday. What documents do I bring, and when do I get my laptop?",
        "profile": EmployeeProfile(),
        "expected_departments": ["hr", "it"],
        "key_points": [
            "document list", "laptop on day 1",
            "accounts before joining if requested 5 working days ahead",
            "otherwise within 2 working days",
        ],
    },
    {
        "id": 9,
        "question": "Can I work from Goa for 3 weeks?",
        "profile": EmployeeProfile(grade="G3", office="Pune", current_city="Goa"),
        "expected_departments": ["hr", "it"],
        "key_points": [
            "up to 20 working days a year", "manager approval", "5 working days ahead",
            "VPN required", "public Wi-Fi only with VPN",
        ],
    },
    {
        "id": 10,
        "question": "I want to work from Dubai for 2 weeks. Is that allowed?",
        "profile": EmployeeProfile(grade="G4", current_city="Dubai"),
        "expected_departments": ["hr", "it"],
        "key_points": [
            "HR Business Partner and IT Security approval", "maximum 15 working days a year",
            "Overseas Access ticket 10 working days before", "sanctioned-country check",
        ],
    },
    {
        "id": 11,
        "question": "I'm resigning. What happens with notice, my laptop and final settlement?",
        "profile": EmployeeProfile(grade="G4"),
        "expected_departments": ["hr", "it", "finance"],
        "key_points": [
            "60 days notice", "EL in notice needs HR Head approval", "up to 30 days EL encashed",
            "return assets on last day", "accounts off at 18:00", "IT clearance to Finance in 2 working days",
            "settlement within 45 days",
        ],
    },
    {
        "id": 12,
        "question": "I'm moving from Pune to the Mumbai office next month. What do I get and what must I do?",
        "profile": EmployeeProfile(grade="G5", office="Pune", joining_date="2024-01-15"),
        "expected_departments": ["hr", "it", "finance"],
        "key_points": [
            "Form HR-12 30 days ahead", "3 days relocation leave", "INR 75,000",
            "travel for dependents", "current accommodation limit with conflict note",
            "goods up to INR 60,000", "lowest of 3 quotes", "laptop in cabin bag",
            "Desk Setup ticket 10 working days ahead", "new access card",
        ],
    },
    {
        "id": 13,
        "question": "I relocated 8 months ago and now I'm resigning. Do I repay anything?",
        "profile": EmployeeProfile(grade="G5"),
        "expected_departments": ["finance"],  # hr optional per assignment
        "key_points": [
            "4 unserved months", "4/12 of INR 75,000", "INR 25,000",
            "recovered in final settlement",
        ],
    },
    {
        "id": 14,
        "question": "How many nights of temporary accommodation do I get when relocating?",
        "profile": EmployeeProfile(),
        "expected_departments": ["hr", "finance"],
        "key_points": [
            "current limit", "10 nights", "clause that sets it",
            "mentions the other document's value and why it no longer applies",
        ],
    },
    {
        "id": 15,
        "question": "What is the policy on sabbatical leave?",
        "profile": EmployeeProfile(),
        "expected_departments": ["hr"],
        "key_points": ["not covered", "HR Business Partner", "no invented details"],
    },
    {
        "id": 16,
        "question": "What is Kestrel's share price today?",
        "profile": EmployeeProfile(),
        "expected_departments": [],
        "key_points": ["politely out of scope", "what the assistant can help with", "no subagent called"],
    },
]

# A small representative subset for `--quick` runs: one single-department
# question per common case (HR/IT/Finance), the highest-value multi-department
# question (relocation, which exercises routing across all 3 departments AND
# the conflict-detection logic), the "not covered" case, and the fully
# out-of-scope case. Useful when free-tier API quotas make running all 16
# questions in one sitting impractical (see eval/run_eval.py --quick).
QUICK_SUBSET_IDS = [1, 2, 5, 12, 15, 16]
