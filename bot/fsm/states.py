from aiogram.fsm.state import State, StatesGroup

class UserFlow(StatesGroup):
    """
    States for the main user's multi-step processes.
    """
    AwaitingClassSelection = State()  # For /start (new user) and /changeclass
    AwaitingSearchQuery = State()    # For "Search for pdf"
    AwaitingAIPrompt = State()       # For "Chat with Ai"
    AwaitingScreenshot = State()     # For the payment flow

class AdminFlow(StatesGroup):
    """
    States for the admin's multi-step commands.
    """
    # For /broadcast
    AwaitingBroadcastMessage = State()
    
    # For the /addpdf command
    AddPDF_AwaitingTitle = State()
    AddPDF_AwaitingLink = State()
    AddPDF_AwaitingClass = State()
    AddPDF_AwaitingFree = State()
    AddPDF_AwaitingKeywords = State()
    DeletePDF_AwaitingConfirmation = State()