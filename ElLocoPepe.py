# app.py — Crazy Joe (Memory-Only)
import math, random, time, threading
from datetime import datetime
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
DEFAULT_SLOTS = 2           # default slots if a member is new
ALLIANCE_PASSCODE = "YosyLion"      # optional: e.g. "FROSTBITE" to gate admin actions ("" disables)
MAX_INCOMING_CAP = None     # set an int to hard-cap incoming per target (None = auto capacity)

st.set_page_config(page_title="TMR Alliance - EL Loco Pepe!", page_icon="🧊", layout="wide")

# ---------------------------
# Shared in-memory store
# ---------------------------
class Store:
    def __init__(self):
        self.lock = threading.Lock()
        # Members: name -> dict(power, slots_to_send, online, updated_at)
        self.members = {}
        # Assignments: sender -> [targets]; batch_id marks last saved set
        self.assignments = {}
        self.batch_id = None
        self.locked = False
        # Assignment mode: "balanced" or "power_based"
        self.assignment_mode = "balanced"

@st.cache_resource(show_spinner=False)
def get_store() -> Store:
    return Store()

store = get_store()

# ---------------------------
# Helpers
# ---------------------------
def parse_power(power_input):
    """Parse power input - automatically treats all input as millions (e.g., '125' -> 125000000)"""
    if isinstance(power_input, (int, float)):
        return int(power_input * 1_000_000)
    
    power_str = str(power_input).strip().upper()
    if power_str.endswith('M'):
        # Remove 'M' and multiply by 1,000,000
        base_value = float(power_str[:-1])
        return int(base_value * 1_000_000)
    else:
        # Treat as millions automatically
        base_value = float(power_str)
        return int(base_value * 1_000_000)

def upsert_member(name: str, power, slots: int, online: bool, x_coord: int = 0, y_coord: int = 0):
    now = datetime.utcnow().isoformat()
    with store.lock:
        rec = store.members.get(name.strip(), {})
        rec.update({
            "power": parse_power(power),
            "slots_to_send": int(slots),
            "online": bool(online),
            "x_coord": int(x_coord),
            "y_coord": int(y_coord),
            "updated_at": now,
        })
        store.members[name.strip()] = rec

def set_all_online(status: bool):
    with store.lock:
        for n, rec in store.members.items():
            rec["online"] = bool(status)
            rec["updated_at"] = datetime.utcnow().isoformat()

def members_df() -> pd.DataFrame:
    with store.lock:
        if not store.members:
            return pd.DataFrame(columns=["name","power","slots_to_send","online","x_coord","y_coord","updated_at"])
        rows = [{"name": n, **rec} for n, rec in store.members.items()]
    df = pd.DataFrame(rows)
    
    # Ensure all required columns exist, add defaults for missing ones
    required_cols = ["name","power","slots_to_send","online","x_coord","y_coord","updated_at"]
    for col in required_cols:
        if col not in df.columns:
            if col in ["x_coord", "y_coord"]:
                df[col] = 0
            else:
                df[col] = ""
    
    df = df[required_cols].sort_values("power", ascending=False)
    
    # Convert power to millions for display
    df["power"] = (df["power"] / 1_000_000).round(1)
    
    return df.reset_index(drop=True)

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
    """Balanced distribution: ensures equal reinforcement distribution."""
    senders = online_df.copy()
    targets = online_df.copy()

    total_slots = int(senders["slots_to_send"].sum())
    if MAX_INCOMING_CAP is None:
        cap = max(1, math.ceil(total_slots / max(1, len(targets))))
    else:
        cap = int(MAX_INCOMING_CAP)
    remaining = {row["name"]: cap for _, row in targets.iterrows()}

    # Round-robin distribution for maximum balance
    target_names = targets.sort_values("power", ascending=False)["name"].tolist()
    result = {s: [] for s in senders["name"].tolist()}
    
    sender_slots = []
    for _, sender in senders.iterrows():
        for _ in range(int(sender["slots_to_send"])):
            sender_slots.append(sender["name"])
    
    random.shuffle(sender_slots)
    
    target_index = 0
    for sender in sender_slots:
        attempts = 0
        while attempts < len(target_names):
            target = target_names[target_index % len(target_names)]
            if target != sender and remaining.get(target, 0) > 0:
                result[sender].append(target)
                remaining[target] -= 1
                target_index += 1
                break
            target_index += 1
            attempts += 1
    
    return result

def compute_power_based_assignments(online_df: pd.DataFrame) -> dict:
    """Power-based matching: reinforces allies with similar power levels."""
    senders = online_df.copy()
    targets = online_df.copy()

    total_slots = int(senders["slots_to_send"].sum())
    if MAX_INCOMING_CAP is None:
        cap = max(1, math.ceil(total_slots / max(1, len(targets))) + 1)
    else:
        cap = int(MAX_INCOMING_CAP)
    remaining = {row["name"]: cap for _, row in targets.iterrows()}

    # Precompute nearest target names for each sender
    nearest = {}
    for _, s in senders.iterrows():
        cand = []
        for _, t in targets.iterrows():
            if s["name"] == t["name"]:
                continue
            cand.append((t["name"], abs(int(s["power"]) - int(t["power"]))))
        cand.sort(key=lambda x: x[1])
        nearest[s["name"]] = [n for (n, _) in cand]

    # Randomize sender order slightly to reduce bias
    sender_names = senders["name"].tolist()
    random.shuffle(sender_names)

    result = {s: [] for s in sender_names}
    for s in sender_names:
        k = int(senders.loc[senders["name"] == s, "slots_to_send"].iloc[0])
        for t in nearest[s]:
            if remaining.get(t, 0) > 0 and len(result[s]) < k:
                result[s].append(t)
                remaining[t] -= 1
            if len(result[s]) >= k:
                break
    return result

def save_assignments(assign_map: dict):
    with store.lock:
        store.assignments = {k:list(v) for k,v in assign_map.items()}
        store.batch_id = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def assignments_df() -> pd.DataFrame:
    with store.lock:
        if not store.assignments:
            return pd.DataFrame(columns=["sender","targets"])
        
        # Get member coordinates for display
        member_coords = {}
        for name, rec in store.members.items():
            x = rec.get("x_coord", 0)
            y = rec.get("y_coord", 0)
            member_coords[name] = f"({x},{y})"
        
        rows = []
        for s, tgts in store.assignments.items():
            # Format targets with coordinates
            target_list = []
            for t in tgts:
                coords = member_coords.get(t, "(0,0)")
                target_list.append(f"{t} {coords}")
            rows.append({"sender": s, "targets": ", ".join(target_list)})
        
        df = pd.DataFrame(rows).sort_values("sender").reset_index(drop=True)
        return df

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

def reset_event():
    with store.lock:
        store.members.clear()
        store.assignments.clear()
        store.batch_id = None
        store.locked = False

# ---------------------------
# UI
# ---------------------------
st.title("🧊 TMR Alliance - EL Loco Pepe!")
st.caption("Crazy Joe Roster and Reinforcement Assignments - Made by Cirtcele")


# Instructions
with st.expander("📋 How to Use This App", expanded=False):
    st.markdown("""
    **🎯 For Alliance Members:**
    1. **📝 Register Once**: Enter your name, power (in millions), slots to send, and coordinates
    2. **💪 Choose Slots Wisely**: 
       - **🔥 Stronger players (50M+)**: Use 4-5 slots to send more reinforcements
       - **⚡ Weaker players (under 50M)**: Use 2-3 slots to avoid overextending
    3. **👥 View Roster**: See all registered members and their power levels
    4. **🎯 Check Assignments**: See who you should reinforce and who will reinforce you
    5. **⏰ Event Duration**: Your registration lasts for the entire event (about a week)
    6. **📍 Use Coordinates**: Find allies easily with their X,Y coordinates
    
    **For Admins:**
    1. **Enter Password**: Use the admin password in the sidebar
    2. **Choose Mode**: Select between Balanced Distribution or Power-Based Matching
    3. **Lock Board**: Prevent assignment changes during events
    4. **Reset Event**: Clear all data when event ends
    
    **Assignment Modes:**
    - **Balanced**: Everyone gets equal reinforcements (fair play)
    - **Power-Based**: Reinforce allies with similar power (max scoring)
    """)

# Auto-refresh to keep everyone in sync
st.sidebar.write(f"⏱ Last refresh: {datetime.now().strftime('%H:%M:%S')}")
st.sidebar.write(f"🔁 Auto-refresh every {REFRESH_SECONDS}s")
st.sidebar.button("Refresh now")
st.sidebar.markdown("---")

if ALLIANCE_PASSCODE:
    code = st.sidebar.text_input("Password (R4 + R5)", type="password")
    authed = (code.strip() == ALLIANCE_PASSCODE)
else:
    authed = True

# Member registration form
st.subheader("📝 Register for Crazy Joe Event")

with st.form("me_form", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns([2,1.4,1,1.3])
    with c1:
        my_name = st.text_input(
            "Your Name", 
            placeholder="Enter your exact in-game name",
            help="Use your exact in-game name so others can find you"
        )
    with c2:
        my_power = st.text_input(
            "Your Power (M)", 
            value="0", 
            placeholder="e.g., 125 or 24.5",
            help="Enter your current power in millions. Just the number (e.g., 125 for 125M power)"
        )
    with c3:
        my_slots = st.selectbox(
            "Slots to Send", 
            options=[2,3,4,5], 
            index=0,
            help="How many reinforcements you can send. Stronger players (50M+) should use 4-5 slots, weaker players use 2-3 slots"
        )
    with c4:
        st.write("")  # Empty space for layout balance
    
    # Location coordinates
    st.markdown("**Your Location**")
    col_x, col_y = st.columns([1, 1])
    with col_x:
        my_x = st.text_input(
            "X Coordinate", 
            value="0",
            max_chars=3,
            help="Your X coordinate in the game (0-999)",
            key="coord_x"
        )
    with col_y:
        my_y = st.text_input(
            "Y Coordinate", 
            value="0",
            max_chars=3,
            help="Your Y coordinate in the game (0-999)",
            key="coord_y"
        )
    
    submitted = st.form_submit_button("🎯 Register for Event", help="By registering, you commit to being online and reinforcing alliance members during the event", use_container_width=True)

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
        
        if not my_power.strip():
            errors.append("⚡ **Power is required** - Enter your power level (e.g., 125 or 24.5)")
        elif not my_power.replace('.', '').replace('M', '').isdigit():
            errors.append("⚡ **Invalid power format** - Use numbers only (e.g., 125 or 24.5)")
        
        if not my_x.strip() or my_x.strip() == "0":
            errors.append("📍 **X coordinate is required** - Enter your X coordinate (000-999)")
        elif not my_x.isdigit() or len(my_x) != 3:
            errors.append("📍 **X coordinate must be exactly 3 digits** - Enter 000-999")
        elif not (0 <= int(my_x) <= 999):
            errors.append("📍 **X coordinate out of range** - Must be between 000-999")
        
        if not my_y.strip() or my_y.strip() == "0":
            errors.append("📍 **Y coordinate is required** - Enter your Y coordinate (000-999)")
        elif not my_y.isdigit() or len(my_y) != 3:
            errors.append("📍 **Y coordinate must be exactly 3 digits** - Enter 000-999")
        elif not (0 <= int(my_y) <= 999):
            errors.append("📍 **Y coordinate out of range** - Must be between 000-999")
        
        if errors:
            st.error("**Please fix the following issues:**")
            for error in errors:
                st.error(error)
        else:
            try:
                # All validation passed, register the member
                x_coord = int(my_x)
                y_coord = int(my_y)
                upsert_member(my_name.strip(), my_power, int(my_slots), True, x_coord, y_coord)
                st.success("✅ **Registration Successful!** You're now registered for the Crazy Joe event.")
            except ValueError as e:
                st.error(f"❌ **Registration failed:** {str(e)}")

df = members_df()

# Check if board is locked for event status
with store.lock:
    current_locked = store.locked

if current_locked:
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
    online_df = df[df["online"]].copy()
    assign_map = compute_assignments(online_df)
    save_assignments(assign_map)
    st.success(f"Assignments recalculated (batch {store.batch_id} UTC).")

# Show saved assignments, or a live preview if none saved yet
saved = assignments_df()
if saved.empty:
    preview = df[df["online"]].copy()
    if not preview.empty:
        pre_map = compute_assignments(preview)
        # Get member coordinates for preview
        member_coords = {}
        for name, rec in store.members.items():
            x = rec.get("x_coord", 0)
            y = rec.get("y_coord", 0)
            member_coords[name] = f"({x},{y})"
        
        pre_rows = []
        for s, tgts in pre_map.items():
            target_list = []
            for t in tgts:
                coords = member_coords.get(t, "(0,0)")
                target_list.append(f"{t} {coords}")
            pre_rows.append({"sender": s, "targets": ", ".join(target_list)})
        
        st.info("No saved batch yet. Showing live preview (not locked).")
        st.dataframe(pd.DataFrame(pre_rows).sort_values("sender").reset_index(drop=True),
                     use_container_width=True)
    else:
        st.write("—")
else:
    if store.batch_id:
        st.caption(f"Batch: **{store.batch_id} UTC**")
    st.dataframe(saved, use_container_width=True)

st.divider()

# Event Participants (moved to bottom for mobile)
st.subheader("👥 Event Participants")
registered_count = len(df[df["online"]])
total_count = len(df)
st.metric("Registered Members", f"{registered_count}/{total_count}")

if registered_count > 0:
    # Show participants with remove buttons for admins
    if authed:
        st.info("🔧 **Admin Mode**: You can remove individual players below")
        for idx, row in df[df["online"]].iterrows():
            col1, col2, col3 = st.columns([3, 1, 0.5])
            with col1:
                st.write(f"**{row['name']}** - Power: {row['power']}M - Slots: {row['slots_to_send']} - Location: ({row['x_coord']},{row['y_coord']})")
            with col2:
                if st.button("❌ Remove", key=f"remove_{row['name']}", type="secondary"):
                    remove_member(row['name'])
                    st.success(f"Removed {row['name']} from the event")
                    st.rerun()
            with col3:
                st.write("")  # Spacer
    else:
        st.dataframe(df[df["online"]].reset_index(drop=True), use_container_width=True)
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
        
        # Assignment mode selector
        with store.lock:
            current_mode = getattr(store, 'assignment_mode', 'balanced')
        mode_options = {
            "Balanced Distribution": "balanced",
            "Power-Based Matching": "power_based"
        }
        selected_mode = st.selectbox(
            "🎯 Assignment Mode", 
            options=list(mode_options.keys()),
            index=list(mode_options.values()).index(current_mode),
            disabled=not authed,
            help="**Balanced**: Equal distribution among all allies (fair play)\n**Power-Based**: Reinforce allies with similar power levels (max scoring)"
        )
        new_mode = mode_options[selected_mode]
        if new_mode != current_mode and authed:
            with store.lock:
                store.assignment_mode = new_mode
            st.success(f"✅ Assignment mode changed to: {selected_mode}")
        
        # Lock board toggle
        with store.lock:
            current_locked = store.locked
        new_locked = st.toggle(
            "🔒 Lock Board", 
            value=current_locked, 
            disabled=not authed,
            help="When locked, assignments won't change until unlocked. Use during events to prevent changes."
        )
        if new_locked != current_locked and authed:
            with store.lock:
                store.locked = new_locked
        if new_locked:
            st.warning("🔒 Board is now LOCKED - assignments won't change")
        else:
            st.success("🔓 Board is now UNLOCKED - assignments can be recalculated")
        
        st.divider()
        
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
