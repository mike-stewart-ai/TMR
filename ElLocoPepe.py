# app.py — Crazy Joe (Memory-Only)
import random, threading
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

# ---------------------------
# Custom CSS for Better Mobile Experience
# ---------------------------
st.markdown("""
<style>
    /* Mobile-friendly improvements */
    .stForm {
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 12px;
        padding: 20px;
        background: rgba(255, 255, 255, 0.05);
    }
    
    /* Better button spacing on mobile */
    .stButton > button {
        margin: 2px 0;
        min-height: 44px; /* iOS recommended touch target */
        padding: 12px 16px;
    }
    
    /* Improve mobile touch targets */
    .stTextInput input,
    .stSelectbox select,
    .stNumberInput input {
        min-height: 44px;
        font-size: 16px; /* Prevents zoom on iOS */
    }
    
    /* Improve dataframe readability */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Hide increment/decrement buttons on number inputs */
    .stNumberInput input[type="number"]::-webkit-outer-spin-button,
    .stNumberInput input[type="number"]::-webkit-inner-spin-button {
        -webkit-appearance: none;
        margin: 0;
    }
    
    .stNumberInput input[type="number"] {
        -moz-appearance: textfield;
    }
    
    /* Additional CSS to hide spin buttons */
    input[type="number"]::-webkit-outer-spin-button,
    input[type="number"]::-webkit-inner-spin-button {
        -webkit-appearance: none;
        margin: 0;
    }
    
    input[type="number"] {
        -moz-appearance: textfield;
    }
    
    
    
    /* Green register button - target form submit buttons */
    .stForm button[type="submit"],
    .stForm .stButton > button,
    div[data-testid="stForm"] button {
        background: linear-gradient(135deg, #28a745 0%, #34ce57 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    
    .stForm button[type="submit"]:hover,
    .stForm .stButton > button:hover,
    div[data-testid="stForm"] button:hover {
        background: linear-gradient(135deg, #218838 0%, #2db84a 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3) !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Config (tweak as you like)
# ---------------------------
REFRESH_SECONDS = 10        # live feel for viewers
ALLIANCE_PASSCODE = "YosyLion"  # Admin password for accessing admin tools

st.set_page_config(page_title="TMR Alliance - EL Loco Pepe!", page_icon="🧊", layout="wide")

# ---------------------------
# Shared in-memory store
# ---------------------------
class Store:
    def __init__(self):
        self.lock = threading.Lock()
        # Members: name -> dict(furnace_level, rallies_to_send, updated_at)
        self.members = {}
        # Assignments: sender -> [targets]; batch_id marks last saved set
        self.assignments = {}
        self.batch_id = None
        self.locked = False
        # Assignment mode: "balanced" or "power_based"
        self.assignment_mode = "power_based"
        # Event time management
        self.event_time = None  # datetime object for event start time

@st.cache_resource(show_spinner=False)
def get_store() -> Store:
    return Store()

store = get_store()

# ---------------------------
# Helpers
# ---------------------------
def parse_furnace_level(furnace_input):
    """Parse furnace level input - accepts values 1-30"""
    if isinstance(furnace_input, (int, float)):
        level = int(furnace_input)
    else:
        level = int(str(furnace_input).strip())
    
    # Validate furnace level is between 1-30
    if not (1 <= level <= 30):
        raise ValueError(f"Furnace level must be between 1-30, got {level}")
    
    return level

def get_furnace_group(furnace_level):
    """Get furnace group based on level"""
    if 1 <= furnace_level <= 25:
        return "Group 1 (1-25)"
    elif 26 <= furnace_level <= 29:
        return "Group 2 (26-29)"
    elif furnace_level == 30:
        return "Group 3 (30)"
    else:
        return "Unknown"

def get_furnace_group_number(furnace_level):
    """Get furnace group number (1, 2, or 3) for sorting purposes"""
    if 1 <= furnace_level <= 25:
        return 1
    elif 26 <= furnace_level <= 29:
        return 2
    elif furnace_level == 30:
        return 3
    else:
        return 1  # Default fallback

def calculate_marches(furnace_level):
    """Calculate number of marches based on furnace level"""
    if 1 <= furnace_level <= 25:
        return 2  # Group 1: 2 marches
    elif 26 <= furnace_level <= 29:
        return 3  # Group 2: 3 marches
    elif furnace_level == 30:
        return 4  # Group 3: 4 marches
    else:
        return 2  # Default fallback

def upsert_member(name: str, furnace_level):
    now = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S UTC")
    with store.lock:
        rec = store.members.get(name.strip(), {})
        furnace_lvl = parse_furnace_level(furnace_level)
        rec.update({
            "furnace_level": furnace_lvl,
            "furnace_group": get_furnace_group(furnace_lvl),
            "rallies_to_send": calculate_marches(furnace_lvl),
            "updated_at": now,
        })
        store.members[name.strip()] = rec


def members_df() -> pd.DataFrame:
    with store.lock:
        if not store.members:
            return pd.DataFrame(columns=["name","furnace_level","furnace_group","marches","updated_at"])
        rows = [{"name": n, **rec} for n, rec in store.members.items()]
    df = pd.DataFrame(rows)
    
    # Rename rallies_to_send to marches for display
    if "rallies_to_send" in df.columns:
        df = df.rename(columns={"rallies_to_send": "marches"})
    
    # Ensure all required columns exist, add defaults for missing ones
    required_cols = ["name","furnace_level","furnace_group","marches","updated_at"]
    for col in required_cols:
        if col not in df.columns:
            if col == "marches":
                df[col] = 2  # Default marches
            else:
                df[col] = ""
    
    df = df[required_cols].sort_values("furnace_level", ascending=False)
    
    # Reset index to start from 1 instead of 0
    df = df.reset_index(drop=True)
    df.index = df.index + 1
    
    return df

def compute_assignments(online_df: pd.DataFrame) -> dict:
    """
    Returns dict: sender -> [targets]
    Two modes available:
    - "balanced": Equal distribution for maximum alliance benefit
    - "power_based": Nearest power matching for optimal Crazy Joe scoring
    """
    if online_df.empty:
        return {}

    with store.lock:
        mode = getattr(store, 'assignment_mode', 'balanced')

    if mode == "balanced":
        return compute_balanced_assignments(online_df)
    else:
        return compute_power_based_assignments(online_df)

def compute_balanced_assignments(online_df: pd.DataFrame) -> dict:
    """Balanced distribution: ensure everyone receives roughly equal reinforcements."""
    senders = online_df.copy()
    targets = online_df.copy()

    # Create result dictionary
    result = {s: [] for s in senders["name"].tolist()}
    
    # Track how many reinforcements each target has received
    target_reinforcement_count = {name: 0 for name in targets["name"].tolist()}
    
    # Sort senders by furnace level (highest first) to give priority to stronger players
    senders_sorted = senders.sort_values("furnace_level", ascending=False)
    
    # For each sender, assign their full number of marches
    for _, sender in senders_sorted.iterrows():
        sender_name = sender["name"]
        
        # Handle both "marches" and "rallies_to_send" columns for backward compatibility
        if "marches" in sender:
            marches_to_send = int(sender["marches"])
        elif "rallies_to_send" in sender:
            marches_to_send = int(sender["rallies_to_send"])
        else:
            # Fallback: calculate based on furnace level
            furnace_level = int(sender["furnace_level"])
            marches_to_send = calculate_marches(furnace_level)
        
        # Find available targets, prioritizing those with fewer reinforcements
        available_targets = []
        for _, target in targets.iterrows():
            if target["name"] != sender_name:
                target_name = target["name"]
                reinforcement_count = target_reinforcement_count[target_name]
                available_targets.append((target_name, reinforcement_count))
        
        # Sort by reinforcement count (those with fewer reinforcements first)
        available_targets.sort(key=lambda x: x[1])
        
        # Assign the full number of marches, prioritizing balanced distribution
        for i in range(min(marches_to_send, len(available_targets))):
            target_name = available_targets[i][0]
            result[sender_name].append(target_name)
            target_reinforcement_count[target_name] += 1

    return result

def compute_power_based_assignments(online_df: pd.DataFrame) -> dict:
    """Furnace group-based matching: prioritize same group, fallback to other groups if needed."""
    senders = online_df.copy()
    targets = online_df.copy()

    # Create result dictionary
    result = {s: [] for s in senders["name"].tolist()}
    
    # Sort senders by furnace level (highest first) to give priority to stronger players
    senders = senders.sort_values("furnace_level", ascending=False)
    
    # For each sender, assign their requested number of reinforcements
    for _, sender in senders.iterrows():
        sender_name = sender["name"]
        sender_furnace_level = sender["furnace_level"]
        sender_group = get_furnace_group_number(sender_furnace_level)
        
        # Handle both "marches" and "rallies_to_send" columns for backward compatibility
        if "marches" in sender:
            marches_to_send = int(sender["marches"])
        elif "rallies_to_send" in sender:
            marches_to_send = int(sender["rallies_to_send"])
        else:
            # Fallback: calculate based on furnace level
            marches_to_send = calculate_marches(sender_furnace_level)
            
        # Find targets with priority: same group first, then other groups
        same_group_targets = []
        other_group_targets = []
        
        for _, target in targets.iterrows():
            if target["name"] != sender_name:  # Only exclude self, allow multiple reinforcements
                target_group = get_furnace_group_number(target["furnace_level"])
                furnace_diff = abs(sender_furnace_level - target["furnace_level"])
                
                if target_group == sender_group:
                    same_group_targets.append((target["name"], furnace_diff))
                else:
                    other_group_targets.append((target["name"], furnace_diff))
        
        # Sort by furnace level difference (closest level first)
        same_group_targets.sort(key=lambda x: x[1])
        other_group_targets.sort(key=lambda x: x[1])
        
        # Combine targets: same group first, then other groups
        all_targets = same_group_targets + other_group_targets
        
        # Assign the requested number of reinforcements
        for i in range(min(marches_to_send, len(all_targets))):
            target_name = all_targets[i][0]
            result[sender_name].append(target_name)

    return result

def save_assignments(assign_map: dict):
    with store.lock:
        store.assignments = {k:list(v) for k,v in assign_map.items()}
        store.batch_id = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S UTC")

def assignments_df() -> pd.DataFrame:
    with store.lock:
        if not store.assignments:
            return pd.DataFrame(columns=["sender","targets"])
        
        rows = []
        for s, tgts in store.assignments.items():
            rows.append({"sender": s, "targets": ", ".join(tgts)})
        
        df = pd.DataFrame(rows).sort_values("sender").reset_index(drop=True)
        # Start row numbering from 1 instead of 0
        df.index = df.index + 1
        return df

def format_reinforcement_plan() -> str:
    """Format the current reinforcement plan for in-game copy-paste use"""
    with store.lock:
        if not store.assignments:
            return "No assignments available. Please recalculate assignments first."
        
        plan_lines = []
        
        # Sort assignments by sender name for consistency
        sorted_assignments = sorted(store.assignments.items())
        
        for sender, targets in sorted_assignments:
            if targets:  # Only show if there are targets
                targets_str = ",".join(targets)  # No spaces to save characters
                plan_lines.append(f"{sender}:{targets_str}")  # Use colon for compactness
        
        # Join with explicit line breaks and add extra newline at end
        return "\n".join(plan_lines) + "\n"

def format_reinforcement_plan_chunks(max_chars=512):
    """Format the reinforcement plan in chunks for games with character limits"""
    full_plan = format_reinforcement_plan()
    
    if len(full_plan) <= max_chars:
        return [full_plan]  # Return as single chunk if under limit
    
    # Split into chunks
    chunks = []
    current_chunk = ""
    
    for line in full_plan.strip().split("\n"):
        if not line.strip():  # Skip empty lines
            continue
            
        # Check if adding this line would exceed the limit
        if len(current_chunk) + len(line) + 1 > max_chars and current_chunk:
            # Start a new chunk
            chunks.append(current_chunk.strip())
            current_chunk = line
        else:
            # Add to current chunk
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line
    
    # Add the last chunk
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def remove_member(name: str):
    with store.lock:
        if name in store.members:
            del store.members[name]
            # Also remove from assignments if they were a sender
            if name in store.assignments:
                del store.assignments[name]
            # Remove them from other people's target lists
            for sender, targets in store.assignments.items():
                if name in targets:
                    targets.remove(name)

def update_member_marches(name: str, new_marches: int):
    """Update the number of marches for a specific member"""
    with store.lock:
        if name in store.members:
            store.members[name]["rallies_to_send"] = int(new_marches)
            store.members[name]["updated_at"] = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S UTC")
            return True
    return False

def set_event_time(time_str: str):
    """Set the event time from a time string in HH:MM format (assumes today)"""
    try:
        # Parse HH:MM format
        hour, minute = map(int, time_str.split(':'))
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            return False
        
        # Set event time for today at the specified time (in UTC)
        today = datetime.now(timezone.utc).date()
        event_time = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
        # Ensure the event time is timezone-aware (UTC)
        event_time = event_time.replace(tzinfo=timezone.utc)
        
        with store.lock:
            store.event_time = event_time
        return True
    except (ValueError, IndexError):
        return False

def get_time_until_event():
    """Get time remaining until event start"""
    with store.lock:
        # Ensure event_time attribute exists
        if not hasattr(store, 'event_time'):
            store.event_time = None
        
        if not store.event_time:
            return None
        
        # Ensure event_time is timezone-aware (fix for existing naive datetimes)
        if store.event_time.tzinfo is None:
            store.event_time = store.event_time.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        time_diff = store.event_time - now
        
        if time_diff.total_seconds() <= 0:
            return "Event has started!"
        
        days = time_diff.days
        hours, remainder = divmod(time_diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m {seconds}s"

def should_auto_lock():
    """Check if board should be automatically locked (5 minutes before event)"""
    with store.lock:
        # Ensure event_time attribute exists
        if not hasattr(store, 'event_time'):
            store.event_time = None
        
        if not store.event_time or store.locked:
            return False
        
        # Ensure event_time is timezone-aware (fix for existing naive datetimes)
        if store.event_time.tzinfo is None:
            store.event_time = store.event_time.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        time_until_event = store.event_time - now
        
        # Auto-lock 5 minutes before event
        return time_until_event.total_seconds() <= 300  # 5 minutes = 300 seconds

def simulate_40_players():
    """Simulate 40 players with random furnace levels 20-30 for testing"""
    import random
    
    # Clear existing data
    with store.lock:
        store.members.clear()
        store.assignments.clear()
        store.batch_id = None
        store.locked = False
    
    # Generate 40 random players
    player_names = [
        "Adam", "Amelia", "Bimba", "Cuse", "Llama", "Mark", "Mike", "Mob", "Test", "Zero",
        "Alex", "Bella", "Chris", "Diana", "Ethan", "Fiona", "George", "Hannah", "Ian", "Julia",
        "Kevin", "Luna", "Max", "Nina", "Oscar", "Paula", "Quinn", "Ruby", "Sam", "Tina",
        "Uma", "Victor", "Wendy", "Xavier", "Yara", "Zoe", "Alpha", "Beta", "Gamma", "Delta"
    ]
    
    for name in player_names:
        # Random furnace level between 20-30
        furnace_level = random.randint(20, 30)
        upsert_member(name, furnace_level)
    
    return f"✅ Simulated 40 players with furnace levels 20-30"

def reset_event():
    with store.lock:
        store.members.clear()
        store.assignments.clear()
        store.batch_id = None
        store.locked = False
        # Ensure event_time attribute exists before setting to None
        if not hasattr(store, 'event_time'):
            store.event_time = None
        else:
            store.event_time = None

# ---------------------------
# UI
# ---------------------------
st.title("🧊 TMR Alliance - EL Loco Pepe!")
st.caption("Crazy Joe Roster and Reinforcement Assignments - Made by Cirtcele")


# Instructions
with st.expander("📋 How to Use This App", expanded=False):
    st.markdown("""
    **🎯 For Alliance Members:**
    1. **📝 Register Once**: Enter your name and furnace level (1-30) - marches are auto-calculated!
    2. **🚀 Auto-March System**: 
       - **🔥 Group 3 (Furnace 30)**: Automatically sends 4 marches
       - **⚡ Group 2 (Furnace 26-29)**: Automatically sends 3 marches
       - **🛡️ Group 1 (Furnace 1-25)**: Automatically sends 2 marches
    3. **👥 View Roster**: See all registered members and their furnace levels/groups
    4. **🎯 Check Assignments**: See who you should reinforce and who will reinforce you
    5. **⏰ Event Timeline**: Register 1 hour before event, board locks 5 minutes before start
    
    **For Admins:**
    1. **Enter Password**: Use the admin password in the sidebar
    2. **Choose Mode**: Select between Balanced Distribution or Power-Based Matching
    3. **Adjust Marches**: Edit individual player marches if needed
    4. **Lock Board**: Lock assignments 5 minutes before event starts
    5. **Copy Plan**: Copy the reinforcement plan and share in-game
    6. **Reset Event**: Clear all data after event ends (data resets for next event)
    
    **📅 Event Process:**
    - **1 Hour Before**: Members register for the event
    - **5 Minutes Before**: Admin locks the board and copies reinforcement plan
    - **Battle Start**: Admin shares the plan in-game, members follow assignments
    - **During Event**: Members send reinforcements to their assigned targets
    - **After Event**: Data is wiped clean for the next event
    
    **Assignment Modes:**
    - **Balanced**: Everyone gets equal reinforcements (fair play)
    - **Furnace-Based**: Reinforce allies with similar furnace levels (max scoring)
    
    **🎯 Reinforcement Rules:**
    - Each player sends their full number of marches based on furnace level
    - Each ally can receive multiple reinforcement marches from different players
    - Balanced mode: Even distribution across all groups
    - Furnace-based mode: Same group priority, then other groups
    """)

# Auto-refresh to keep everyone in sync
st.sidebar.write(f"⏱ Last refresh: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
st.sidebar.write(f"🔁 Auto-refresh every {REFRESH_SECONDS}s")
st.sidebar.button("Refresh now")
st.sidebar.markdown("---")

if ALLIANCE_PASSCODE:
    code = st.sidebar.text_input("Password (R4 + R5)", type="password", key="admin_password")
    if st.sidebar.button("🔓 Login", type="primary", use_container_width=True):
        if code.strip() == ALLIANCE_PASSCODE:
            st.sidebar.success("✅ Admin access granted!")
        else:
            st.sidebar.error("❌ Invalid password")
    authed = (code.strip() == ALLIANCE_PASSCODE)
else:
    authed = True

# Member registration form
st.subheader("📝 Register for Crazy Joe Event")

with st.form("me_form", clear_on_submit=True):
    c1, c2, c3 = st.columns([2,1.4,1.6])
    with c1:
        my_name = st.text_input(
            "Your Name", 
            placeholder="Enter your exact in-game name",
            help="Use your exact in-game name so others can find you"
        )
    with c2:
        my_furnace = st.text_input(
            "Your Furnace Level", 
            value="1", 
            placeholder="e.g., 15 or 28",
            help="Enter your furnace level (1-30). Marches auto-calculated: Group 1 (1-25): 2, Group 2 (26-29): 3, Group 3 (30): 4"
        )
    with c3:
        st.write("")  # Empty space for layout balance
    
    submitted = st.form_submit_button("🎯 Register for Event", help="By registering, you commit to reinforcing alliance members during the event", use_container_width=True)

if submitted:
    # Check if board is locked
    with store.lock:
        current_locked = store.locked
    
    if current_locked:
        st.error("🔒 **Board is LOCKED!** Registration is closed during the event.")
    else:
        # Validate all fields are filled with better error messages
        errors = []
        
        if not my_name.strip():
            errors.append("📝 **Name is required** - Enter your exact in-game name")
        elif len(my_name.strip()) < 2:
            errors.append("📝 **Name too short** - Enter at least 2 characters")
        
        if not my_furnace.strip():
            errors.append("🔥 **Furnace level is required** - Enter your furnace level (1-30)")
        elif not my_furnace.isdigit():
            errors.append("🔥 **Invalid furnace level** - Use numbers only (1-30)")
        else:
            try:
                furnace_level = int(my_furnace)
                if not (1 <= furnace_level <= 30):
                    errors.append("🔥 **Furnace level out of range** - Must be between 1-30")
            except ValueError:
                errors.append("🔥 **Invalid furnace level** - Use numbers only (1-30)")
        
        if errors:
            st.error("**Please fix the following issues:**")
            for error in errors:
                st.error(error)
        else:
            try:
                # All validation passed, register the member
                upsert_member(my_name.strip(), my_furnace)
                st.success("✅ **Registration Successful!** You're now registered for the Crazy Joe event.")
            except ValueError as e:
                st.error(f"❌ **Registration failed:** {str(e)}")

df = members_df()

# Check if board is locked for event status
with store.lock:
    current_locked = store.locked

# Event countdown and status display
with store.lock:
    # Ensure event_time attribute exists
    if not hasattr(store, 'event_time'):
        store.event_time = None
    event_time = store.event_time
    board_locked = store.locked

if event_time:
    time_remaining = get_time_until_event()
    
    if time_remaining == "Event has started!":
        st.markdown("""
        <div style="background-color: #ff4444; color: white; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 10px;">
            <h3 style="margin: 0; color: white;">🚀 EVENT STARTED</h3>
            <p style="margin: 5px 0 0 0; font-size: 14px; color: #ffcccc;">Board locked - assignments are final</p>
        </div>
        """, unsafe_allow_html=True)
    elif board_locked:
        st.markdown("""
        <div style="background-color: #ff8800; color: white; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 10px;">
            <h3 style="margin: 0; color: white;">🔒 BOARD LOCKED</h3>
            <p style="margin: 5px 0 0 0; font-size: 14px; color: #ffddcc;">Event starts in: """ + time_remaining + """</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background-color: #0088ff; color: white; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 10px;">
            <h3 style="margin: 0; color: white;">⏰ EVENT COUNTDOWN</h3>
            <p style="margin: 5px 0 0 0; font-size: 14px; color: #ccddff;">Event starts in: """ + time_remaining + """</p>
        </div>
        """, unsafe_allow_html=True)
elif current_locked:
    st.markdown("""
    <div style="background-color: #ff4444; color: white; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 10px;">
        <h3 style="margin: 0; color: white;">🚀 EVENT STARTED</h3>
        <p style="margin: 5px 0 0 0; font-size: 14px; color: #ffcccc;">Board locked - assignments are final</p>
    </div>
    """, unsafe_allow_html=True)

st.subheader("🎯 Reinforcement Assignments")
# Recalc button
can_recalc = not current_locked
if st.button("Recalculate assignments", type="primary", disabled=not can_recalc):
    assign_map = compute_assignments(df)
    save_assignments(assign_map)
    st.success(f"Assignments recalculated (batch {store.batch_id} UTC).")

# Show saved assignments, or a live preview if none saved yet
saved = assignments_df()
if saved.empty:
    preview = df.copy()
    if not preview.empty:
        pre_map = compute_assignments(preview)
        
        pre_rows = []
        for s, tgts in pre_map.items():
            pre_rows.append({"sender": s, "targets": ", ".join(tgts)})
        
        st.info("No saved batch yet. Showing live preview (not locked).")
        preview_df = pd.DataFrame(pre_rows).sort_values("sender").reset_index(drop=True)
        preview_df.index = preview_df.index + 1  # Start from 1
        st.dataframe(preview_df, use_container_width=True)
    else:
        st.write("—")
else:
    if store.batch_id:
        st.caption(f"Batch: **{store.batch_id} UTC**")
    st.dataframe(saved, use_container_width=True)

st.divider()

# Event Participants (moved to bottom for mobile)
st.subheader("👥 Event Participants")
registered_count = len(df)
total_count = len(df)
st.metric("Registered Members", f"{registered_count}/{total_count}")

if registered_count > 0:
    # Show participants with admin controls
    if authed:
        st.info("🔧 **Admin Mode**: You can edit marches and remove players below")
        for idx, row in df.iterrows():
            col1, col2, col3, col4 = st.columns([2.5, 1, 1, 0.5])
            with col1:
                st.write(f"**{row['name']}** - Furnace: {row['furnace_level']} ({row['furnace_group']}) - Marches: {row['marches']}")
            with col2:
                new_marches = st.number_input(
                    "Marches", 
                    min_value=1, 
                    max_value=10, 
                    value=int(row['marches']), 
                    key=f"marches_{row['name']}",
                    help=f"Edit marches for {row['name']}"
                )
                if new_marches != int(row['marches']):
                    if st.button("💾 Update", key=f"update_{row['name']}", type="primary"):
                        if update_member_marches(row['name'], new_marches):
                            st.success(f"Updated {row['name']} to {new_marches} marches")
                            st.rerun()
                        else:
                            st.error(f"Failed to update {row['name']}")
            with col3:
                if st.button("❌ Remove", key=f"remove_{row['name']}", type="secondary"):
                    remove_member(row['name'])
                    st.success(f"Removed {row['name']} from the event")
                    st.rerun()
            with col4:
                st.write("")  # Spacer
    else:
        st.dataframe(df.reset_index(drop=True), use_container_width=True)
else:
    st.info("No members registered yet. Be the first to join the event!")

st.divider()

# Admin: export + reset
with st.expander("🔧 Admin Tools", expanded=False):
    st.info("🔐 **Admin Access Required**: Enter the admin password in the sidebar to unlock these features")
    
    if not authed:
        st.warning("⚠️ Enter the admin password in the sidebar to access these tools")
    else:
        st.success("✅ Admin access granted!")
        
        # Event time management
        st.subheader("⏰ Event Time Management")
        
        # Get current event time
        with store.lock:
            # Ensure event_time attribute exists
            if not hasattr(store, 'event_time'):
                store.event_time = None
            current_event_time = store.event_time
        
        if current_event_time:
            st.info(f"📅 **Event scheduled for:** {current_event_time.strftime('%H:%M UTC today')}")
            
            # Show countdown
            time_remaining = get_time_until_event()
            if time_remaining:
                if time_remaining == "Event has started!":
                    st.error("🚨 **Event has started!**")
                else:
                    st.success(f"⏱️ **Time until event:** {time_remaining}")
        else:
            st.warning("⚠️ **No event time set** - Set the event time below")
        
        # Event time input
        col1, col2 = st.columns([2, 1])
        with col1:
            event_time_input = st.text_input(
                "Event Time (HH:MM format)",
                value=current_event_time.strftime('%H:%M') if current_event_time else "",
                placeholder="19:00",
                help="Enter the event time in HH:MM format (24-hour). Board will auto-lock 5 minutes before."
            )
        with col2:
            if st.button("📅 Set Event Time", type="primary"):
                if event_time_input:
                    if set_event_time(event_time_input):
                        st.success("✅ Event time set successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid time format. Use HH:MM (e.g., 19:00)")
                else:
                    st.error("❌ Please enter an event time")
        
        st.divider()
        
        # Assignment mode selector
        with store.lock:
            current_mode = getattr(store, 'assignment_mode', 'balanced')
        mode_options = {
            "Balanced Distribution": "balanced",
            "Furnace-Based Matching": "power_based"
        }
        selected_mode = st.selectbox(
            "🎯 Assignment Mode", 
            options=list(mode_options.keys()),
            index=list(mode_options.values()).index(current_mode),
            disabled=not authed,
            help="**Balanced**: Equal distribution among all allies (fair play)\n**Furnace-Based**: Reinforce allies with similar furnace levels (max scoring)"
        )
        new_mode = mode_options[selected_mode]
        if new_mode != current_mode and authed:
            with store.lock:
                store.assignment_mode = new_mode
            st.success(f"✅ Assignment mode changed to: {selected_mode}")
        
        # Auto-lock check
        should_lock = should_auto_lock()
        if should_lock and not current_locked:
            with store.lock:
                store.locked = True
            st.warning("🔒 **AUTO-LOCKED!** Board automatically locked 5 minutes before event!")
            st.rerun()
        
        # Lock board toggle
        with store.lock:
            current_locked = store.locked
        
        # Show auto-lock status
        if current_event_time:
            time_until_event = get_time_until_event()
            if time_until_event and time_until_event != "Event has started!":
                # Parse time to check if we're within 5 minutes
                # Ensure current_event_time is timezone-aware
                if current_event_time and current_event_time.tzinfo is None:
                    current_event_time = current_event_time.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                time_diff = current_event_time - now
                if time_diff.total_seconds() <= 300 and time_diff.total_seconds() > 0:
                    st.info(f"⏰ **Auto-lock in:** {time_until_event} (5 minutes before event)")
        
        new_locked = st.toggle(
            "🔒 Lock Board", 
            value=current_locked, 
            disabled=not authed,
            help="When locked, assignments won't change until unlocked. Auto-locks 5 minutes before event."
        )
        if new_locked != current_locked and authed:
            with store.lock:
                store.locked = new_locked
        if new_locked:
            st.warning("🔒 Board is now LOCKED - assignments won't change")
        else:
            st.success("🔓 Board is now UNLOCKED - assignments can be recalculated")
        
        st.divider()
        
        # Reinforcement Plan Copy-Paste Field
        st.subheader("📋 Final Battle Plan - Copy & Share")
        st.info("💡 **5 minutes before event**: Copy the text below and paste it in-game to share the final reinforcement plan with your alliance")
        
        if current_locked:
            st.success("🔒 **Board is LOCKED** - This is your final battle plan!")
        else:
            st.warning("⚠️ **Board is UNLOCKED** - Lock the board 5 minutes before event to finalize the plan")
        
        reinforcement_plan = format_reinforcement_plan()
        
        
        # Game-friendly format (semicolon separated)
        st.subheader("🎮 Game-Friendly Format (Recommended)")
        st.success("✅ **This format works great in the game!**")
        
        # Create game-friendly format with semicolon separators
        alt_plan_lines = []
        for sender, targets in sorted(store.assignments.items()):
            if targets:
                targets_str = ",".join(targets)
                alt_plan_lines.append(f"{sender}->{targets_str}")
        
        alt_plan = "; ".join(alt_plan_lines)
        
        st.text_area(
            "Game-Friendly Format (semicolon separated):",
            value=alt_plan,
            height=200,
            help="This format works perfectly in the game chat - copy and paste directly!"
        )
        
        
        st.divider()
        
        # Test Simulation Button
        if st.button(
            "🧪 Simulate 40 Players (Test)", 
            type="secondary", 
            disabled=not authed,
            help="Generate 40 test players with random furnace levels 20-30"
        ):
            result = simulate_40_players()
            st.success(result)
            st.rerun()
        
        # Reset Event Button
        if st.button(
            "🧹 Reset Event", 
            type="secondary", 
            disabled=not authed,
            help="⚠️ WARNING: This will clear ALL data from memory!"
        ):
            reset_event()
            st.success("✅ Cleared all members and assignments from memory.")
        

st.caption("Note: This version stores everything in memory only. If the app restarts, data resets. Export before you reset/end the event.")
# Simple auto-refresh
st.markdown(
    f"<script>setTimeout(() => window.location.reload(), {REFRESH_SECONDS*1000});</script>",
    unsafe_allow_html=True
)
