"""The shared Memory Management Unit (MMU): L1 cache, L2 DLL, L3 vector store and BMJ routing.

Stores nothing itself (docs/decisions/0015): each side owns its storage under guardian/data or
learner/data, isolated per organisation and per person, behind getters and setters.
"""
