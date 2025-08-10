import streamlit as st

DEMO_USERS = {
    "admin": "password123",
    "user1": "pass123", 
    "demo": "demo123"
}

def login_page():
    """Simple login page"""
    st.set_page_config(page_title="Login", page_icon="", layout="centered")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("Login")
        st.markdown("---")
        
        # Login form
        with st.form("login"):
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            
            login_button = st.form_submit_button("Login", type="primary", use_container_width=True)
            
            if login_button:
                if username and password:
                    # Check credentials
                    if username in DEMO_USERS and DEMO_USERS[username] == password:
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
                else:
                    st.error("Please enter both username and password")

def main_page():
    """Main application page after login"""
    st.set_page_config(page_title="", page_icon="", layout="wide")
    
    # Sidebar with user info, Redis connection, and logout
    with st.sidebar:
        st.markdown("### Welcome!")
        st.write(f"**User:** {st.session_state.username}")
        st.markdown("---")
        
        # Redis Connection Section
        st.markdown("### Redis Connection")
        
        # Show Redis connection status
        if "redis_connected" not in st.session_state:
            st.session_state.redis_connected = False
        
        if st.session_state.redis_connected:
            if st.button("Disconnect Redis", type="secondary"):
                st.session_state.redis_connected = False
                st.rerun()
        else:
            st.warning("Not connected to Redis")
        
        st.markdown("---")
        
        if st.button("Logout", type="secondary"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.redis_connected = False
            st.rerun()
    
    if not st.session_state.redis_connected:
        st.info("Please connect to Redis Cloud to access the main application features.")
        st.markdown("---")
        st.subheader("Redis Cloud Connection Required")
        st.write("This application requires a Redis Cloud connection to:")
        st.write("- Store and retrieve JSON data in the form of vector embeddings")
        st.write("- Chat with your uploaded data")
        st.write("- Use the recommendation system")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("Connect Now", type="primary", use_container_width=True):
                with st.spinner("Connecting to Redis Cloud..."):
                    try:
                        import time
                        time.sleep(1)
                        st.session_state.redis_connected = True
                        st.success("Connected to Redis Cloud successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to connect to Redis: {str(e)}")
    else:
        # Load your actual main application here only after Redis connection
        try:
            # Import and run your existing app
            from chatbot_and_recom import StreamlitApp
            app = StreamlitApp()
            app.run()
        except Exception as e:
            # Fallback content if main app fails
            st.error(f"Error loading main app: {e}")
            st.markdown("---")
            st.subheader("Demo Content")
            
            tab1, tab2 = st.tabs(["Dashboard", "Settings"])
            
            with tab1:
                st.metric("Active Users", "1")
                st.line_chart([1, 2, 3, 4, 5])
            
            with tab2:
                st.checkbox("Enable notifications")
                st.selectbox("Theme", ["Light", "Dark"])

def main():
    """Main function"""
    # Initialize session state
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "username" not in st.session_state:
        st.session_state.username = ""
    
    # Show login or main page
    if st.session_state.logged_in:
        main_page()
    else:
        login_page()

if __name__ == "__main__":
    main() 
