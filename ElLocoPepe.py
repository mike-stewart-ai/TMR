# app.py — Crazy Joe (Memory-Only)
import math, random, time, threading
from datetime import datetime
import pandas as pd
import streamlit as st

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

def upsert_member(name: str, power, slots: int, online: bool):
    now = datetime.utcnow().isoformat()
    with store.lock:
        rec = store.members.get(name.strip(), {})
        rec.update({
            "power": parse_power(power),
            "slots_to_send": int(slots),
            "online": bool(online),
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
            return pd.DataFrame(columns=["name","power","slots_to_send","online","updated_at"])
        rows = [{"name": n, **rec} for n, rec in store.members.items()]
    df = pd.DataFrame(rows)
    df = df[["name","power","slots_to_send","online","updated_at"]].sort_values("power", ascending=False)
    
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
        rows = [{"sender": s, "targets": ", ".join(tgts)} for s, tgts in store.assignments.items()]
        df = pd.DataFrame(rows).sort_values("sender").reset_index(drop=True)
        return df

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
    **For Alliance Members:**
    1. **Register Once**: Enter your name, power (in millions), slots to send, and availability
    2. **Choose Slots Wisely**: 
       - **Stronger players (50M+)**: Use 4-5 slots to send more reinforcements
       - **Weaker players (under 50M)**: Use 2-3 slots to avoid overextending
    3. **View Roster**: See all registered members and their power levels
    4. **Check Assignments**: See who you should reinforce and who will reinforce you
    5. **Event Duration**: Your registration lasts for the entire event (about a week)
    
    **For Admins:**
    1. **Enter Password**: Use the admin password in the sidebar
    2. **Choose Mode**: Select between Balanced Distribution or Power-Based Matching
    3. **Lock Board**: Prevent assignment changes during events
    4. **Export Data**: Download roster and assignments as CSV files
    5. **Reset Event**: Clear all data when event ends
    
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
st.info("💡 **One-time registration**: Register once for the event. Your status will be locked until the next event!")

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
        my_online = st.toggle(
            "I'm Available", 
            value=True,
            help="Toggle ON if you're available for this event"
        )
    submitted = st.form_submit_button("🎯 Register for Event", type="primary")

if submitted and my_name.strip():
    try:
        upsert_member(my_name.strip(), my_power, int(my_slots), bool(my_online))
        st.success("✅ **Registered successfully!** You're now part of the Crazy Joe event. Your status is locked until the next event.")
    except ValueError as e:
        st.error(f"Invalid power value: {my_power}. Please enter a number or number with 'M' suffix (e.g., 128M).")

df = members_df()

left, right = st.columns(2)
with left:
    st.subheader("👥 Event Participants")
    registered_count = len(df[df["online"]])
    total_count = len(df)
    st.metric("Registered Members", f"{registered_count}/{total_count}")
    if registered_count > 0:
        st.dataframe(df[df["online"]].reset_index(drop=True), use_container_width=True)
    else:
        st.info("No members registered yet. Be the first to join the event!")

with right:
    st.subheader("🎯 Reinforcement Assignments")
    # Recalc button
    with store.lock:
        current_locked = store.locked
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
            pre_rows = [{"sender": s, "targets": ", ".join(t)} for s, t in pre_map.items()]
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
        
        st.subheader("📊 Data Management")
        
        c1, c2, c3 = st.columns([1.4,1.2,2])
        with c1:
            # Export current members
            csv_members = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download Roster CSV", 
                csv_members, 
                "crazy_joe_roster.csv",
                disabled=df.empty or not authed,
                help="Download current member roster with power levels and status"
            )
        with c2:
            # Export assignments
            saved = assignments_df()
            csv_assign = saved.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download Assignments CSV", 
                csv_assign, 
                "crazy_joe_assignments.csv",
                disabled=saved.empty or not authed,
                help="Download current reinforcement assignments"
            )
        with c3:
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
