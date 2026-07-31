"""
Customer Support Agent - Streamlit Application
Main UI for the AI-powered customer support system
"""

import streamlit as st
import pandas as pd
import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.data_loader import DataLoader
from src.rag_engine import RAGEngine
from src.response_generator import ResponseGenerator, FeedbackLoop
from src.db import MongoDBClient
from src.translator import detect_language, get_language_name


# Page configuration
st.set_page_config(
    page_title="AI Customer Support Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .category-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.875rem;
        font-weight: 500;
    }
    .priority-urgent { background-color: #FFEBEE; color: #C62828; }
    .priority-high { background-color: #FFF3E0; color: #E65100; }
    .priority-medium { background-color: #E3F2FD; color: #1565C0; }
    .priority-low { background-color: #E8F5E9; color: #2E7D32; }
    .response-card {
        background-color: #F5F5F5;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .similar-ticket {
        background-color: #FAFAFA;
        padding: 1rem;
        border-left: 3px solid #1E88E5;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


def initialize_session_state():
    """Initialize session state variables"""
    if 'rag_engine' not in st.session_state:
        st.session_state.rag_engine = None
    if 'response_generator' not in st.session_state:
        st.session_state.response_generator = None
    if 'feedback_loop' not in st.session_state:
        st.session_state.feedback_loop = None
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'current_response' not in st.session_state:
        st.session_state.current_response = None
    if 'is_initialized' not in st.session_state:
        st.session_state.is_initialized = False
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
    if 'db' not in st.session_state:
        st.session_state.db = None


def get_db():
    """
    Lazily connect to MongoDB, caching the client in session state.

    Returns None when MongoDB is unreachable so the dashboard degrades to the
    RAG-only tabs instead of erroring out.
    """
    if st.session_state.db is not None:
        return st.session_state.db
    try:
        client = MongoDBClient()
        client.connect()
        st.session_state.db = client
        return client
    except Exception as e:
        st.session_state.db = None
        st.session_state.db_error = str(e)
        return None


def load_system(data_path: str = None, force_rebuild: bool = False):
    """
    Load and initialize the support system.

    `force_rebuild` skips the cached FAISS index and re-embeds `data_path`.
    Without it, "Initialize with New Data" found the existing index on disk and
    loaded that instead — the freshly uploaded CSV was never indexed and the
    dashboard kept answering from the old corpus.
    """
    try:
        with st.spinner("🔄 Initializing AI Support System..."):
            # Check for API key
            if not Config.GOOGLE_API_KEY:
                st.error("❌ Google API Key not found. Please set GOOGLE_API_KEY in .env file")
                return False
            
            # Check if vector store exists
            vector_store_path = Config.VECTOR_STORE_PATH
            
            index_exists = os.path.exists(
                os.path.join(vector_store_path, "faiss_index.bin")
            )

            if index_exists and not force_rebuild:
                # Load existing vector store
                st.info("📂 Loading existing vector store...")
                rag_engine = RAGEngine()
                rag_engine.load_from_disk(vector_store_path)
            elif data_path and os.path.exists(data_path):
                # Create new from data
                st.info("📊 Creating new vector store from data...")
                loader = DataLoader(data_path)
                loader.load_data()
                documents = loader.create_documents()
                
                rag_engine = RAGEngine()
                rag_engine.initialize_from_documents(documents)
                rag_engine.save_to_disk(vector_store_path)
            else:
                st.warning("⚠️ No data source found. Please upload a CSV file or provide data path.")
                return False
            
            # Initialize response generator — feedback persists to MongoDB
            # when it is reachable, otherwise it stays in memory.
            response_generator = ResponseGenerator(rag_engine=rag_engine)
            feedback_loop = FeedbackLoop(response_generator, db_client=get_db())
            
            # Store in session state
            st.session_state.rag_engine = rag_engine
            st.session_state.response_generator = response_generator
            st.session_state.feedback_loop = feedback_loop
            st.session_state.is_initialized = True
            
            st.success("✅ AI Support System initialized successfully!")
            return True
            
    except Exception as e:
        st.error(f"❌ Error initializing system: {str(e)}")
        return False


UPLOADED_DATA_PATH = os.path.join("data", "uploaded_tickets.csv")


def process_uploaded_file(uploaded_file):
    """
    Persist an uploaded CSV and confirm it is usable.

    Written to `data/uploaded_tickets.csv`, never to the path the bundled
    dataset lives at: the previous version overwrote
    `data/customer_support_tickets.csv` with whatever the user picked, which
    destroyed the shipped data on the first upload with no way back.

    The file is validated before it is accepted, so a spreadsheet with the
    wrong columns fails here rather than half-way through an embedding run
    that costs real API calls.
    """
    file_path = UPLOADED_DATA_PATH
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Fail fast on an unreadable or wrongly-shaped CSV
        loader = DataLoader(file_path)
        loader.load_data()
        loader.create_documents()

        st.session_state.data_loaded = True
        return file_path

    except Exception as e:
        st.error(f"❌ Could not use that file: {e}")
        try:
            os.remove(file_path)
        except OSError:
            pass
        st.session_state.data_loaded = False
        return None


def render_sidebar():
    """Render the sidebar"""
    st.sidebar.title("⚙️ Settings")
    
    # API Key status
    if Config.GOOGLE_API_KEY:
        st.sidebar.success("✅ API Key configured")
    else:
        st.sidebar.error("❌ API Key missing")
        st.sidebar.text_input(
            "Enter Google API Key",
            type="password",
            key="api_key_input",
            help="Get your API key from Google AI Studio"
        )
    
    st.sidebar.divider()
    
    # Data upload section
    st.sidebar.subheader("📁 Data Management")
    
    uploaded_file = st.sidebar.file_uploader(
        "Upload Support Tickets CSV",
        type=['csv'],
        help="Upload a CSV with 'instruction' and 'response' columns"
    )
    
    if uploaded_file:
        file_path = process_uploaded_file(uploaded_file)
        if file_path:
            st.sidebar.success("✅ File uploaded")
            if st.sidebar.button("🔄 Initialize with New Data"):
                st.session_state.is_initialized = False
                load_system(file_path, force_rebuild=True)
    
    # Initialize button
    if not st.session_state.is_initialized:
        if st.sidebar.button("🚀 Initialize System"):
            load_system(Config.DATA_PATH)
    
    st.sidebar.divider()
    
    # Configuration options
    st.sidebar.subheader("🎛️ Response Settings")
    
    Config.TOP_K_RESULTS = st.sidebar.slider(
        "Number of similar tickets",
        min_value=1,
        max_value=10,
        value=5
    )
    
    Config.TEMPERATURE = st.sidebar.slider(
        "Response creativity",
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        step=0.1
    )
    
    st.sidebar.divider()
    
    # System status
    st.sidebar.subheader("📊 System Status")
    if st.session_state.is_initialized:
        stats = st.session_state.rag_engine.vector_store.get_stats()
        st.sidebar.metric("Documents Indexed", stats['total_documents'])
        st.sidebar.metric("Embedding Dimension", stats['embedding_dimension'])
    else:
        st.sidebar.info("System not initialized")


def render_main_content():
    """Render the main content area"""
    st.markdown('<h1 class="main-header">🤖 AI Customer Support Agent</h1>', unsafe_allow_html=True)
    
    # Check initialization
    if not st.session_state.is_initialized:
        st.info("👋 Welcome! Please initialize the system using the sidebar to get started.")
        
        # Show architecture
        st.subheader("📐 System Architecture")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            ### 1️⃣ Data Processing
            - Load customer support tickets
            - Preprocess and clean text
            - Create document chunks
            """)
        
        with col2:
            st.markdown("""
            ### 2️⃣ Vector Store (FAISS)
            - Generate Gemini embeddings
            - Store in FAISS index
            - Enable similarity search
            """)
        
        with col3:
            st.markdown("""
            ### 3️⃣ RAG + Response
            - Retrieve relevant context
            - Generate with Gemini LLM
            - Categorize and prioritize
            """)
        
        return
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "💬 Support Chat",
        "🎫 Ticket Queue",
        "📊 Ticket Analysis",
        "🔄 Response Sampling",
        "📝 Feedback & History"
    ])

    # Tab 1: Support Chat
    with tab1:
        render_chat_interface()

    # Tab 2: Ticket queue (admin/agent view backed by MongoDB)
    with tab2:
        render_ticket_queue()

    # Tab 3: Ticket Analysis
    with tab3:
        render_analysis_interface()

    # Tab 4: Response Sampling
    with tab4:
        render_sampling_interface()

    # Tab 5: Feedback History
    with tab5:
        render_feedback_interface()


def render_chat_interface():
    """Render the main chat interface"""
    st.subheader("💬 Customer Support Chat")
    
    # Chat input
    user_query = st.text_area(
        "Enter customer query:",
        placeholder="e.g., I haven't received my order yet and it's been 2 weeks...",
        height=100
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        generate_btn = st.button("🚀 Generate Response", type="primary")
    with col2:
        use_rag = st.checkbox("Use RAG context", value=True)
    
    if generate_btn and user_query:
        try:
            with st.spinner("🤔 Analyzing query and generating response..."):
                generator = st.session_state.response_generator
                if use_rag:
                    # Full pipeline: auto-detects language, translates,
                    # categorizes and grounds the answer in similar tickets.
                    result = generator.generate_with_analysis(user_query)
                else:
                    # RAG disabled — answer from the LLM alone
                    lang = detect_language(user_query)
                    result = {
                        "query": user_query,
                        "english_query": user_query,
                        "response": generator.generate_response(user_query, use_rag=False),
                        "categorization": generator.categorize_ticket(user_query),
                        "similar_tickets": [],
                        "language": lang,
                    }
            st.session_state.current_response = result

            # Store in chat history
            st.session_state.chat_history.append({
                "query": user_query,
                "result": result
            })
        except Exception as e:
            st.error(f"❌ Could not generate a response: {e}")

    # Display current response
    if st.session_state.current_response:
        result = st.session_state.current_response

        # Categorization badges
        cat = result.get('categorization', {})
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("Category", cat.get('category', 'N/A'))
        with col2:
            priority = cat.get('priority', 'medium')
            st.metric("Priority", priority.upper())
        with col3:
            st.metric("Sentiment", cat.get('sentiment', 'neutral').capitalize())
        with col4:
            st.metric("Language", get_language_name(result.get('language', 'en')))
        with col5:
            st.metric("Similar Tickets", len(result.get('similar_tickets', [])))
        
        st.divider()
        
        # Response
        st.markdown("### 📝 Generated Response")
        st.markdown(f"""
        <div class="response-card">
        {result['response']}
        </div>
        """, unsafe_allow_html=True)
        
        # Copy button
        st.code(result['response'], language=None)
        
        # Similar tickets expander
        if result.get('similar_tickets'):
            with st.expander("🔍 Similar Tickets Found"):
                for i, ticket in enumerate(result['similar_tickets'], 1):
                    st.markdown(f"""
                    <div class="similar-ticket">
                    <strong>Ticket #{i}</strong> (Similarity: {ticket['similarity_score']:.2%})<br>
                    <strong>Query:</strong> {ticket['instruction'][:200]}...<br>
                    <strong>Response:</strong> {ticket['response'][:200]}...
                    </div>
                    """, unsafe_allow_html=True)


STATUS_LABELS = {
    "open": "🟠 Open",
    "in_progress": "🔵 In Progress",
    "resolved": "🟢 Resolved",
}


def render_ticket_queue():
    """
    Agent/admin view of the live ticket queue backed by MongoDB.

    Lists every ticket with its AI categorization, lets an agent filter by
    status/priority/category and move a ticket through its lifecycle.
    """
    st.subheader("🎫 Ticket Queue")

    db = get_db()
    if db is None:
        st.warning(
            "MongoDB is not reachable, so there is no ticket queue to show. "
            "Set `MONGODB_URI` in your .env and make sure the server is running."
        )
        if st.session_state.get("db_error"):
            st.caption(f"Connection error: {st.session_state.db_error}")
        return

    try:
        tickets = db.get_all_tickets()
        stats = db.get_ticket_stats()
    except Exception as e:
        st.error(f"❌ Could not read tickets: {e}")
        return

    # Headline metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Tickets", stats["total"])
    col2.metric("Open", stats["by_status"].get("open", 0))
    col3.metric("In Progress", stats["by_status"].get("in_progress", 0))
    col4.metric("Resolved", stats["by_status"].get("resolved", 0))

    if not tickets:
        st.info("No tickets yet. Create one from the web frontend or the API.")
        return

    st.divider()

    # Filters
    fcol1, fcol2, fcol3 = st.columns(3)
    status_filter = fcol1.selectbox(
        "Status", ["All", "open", "in_progress", "resolved"], key="q_status"
    )
    priority_filter = fcol2.selectbox(
        "Priority", ["All"] + list(Config.PRIORITY_SLA), key="q_priority"
    )
    category_filter = fcol3.selectbox(
        "Category", ["All"] + Config.TICKET_CATEGORIES, key="q_category"
    )

    def _matches(t):
        return (
            (status_filter == "All" or t.get("status") == status_filter)
            and (priority_filter == "All" or t.get("priority") == priority_filter)
            and (category_filter == "All" or t.get("category") == category_filter)
        )

    filtered = [t for t in tickets if _matches(t)]
    # get_all_tickets() returns a bounded page, so say so rather than implying
    # `len(tickets)` is the whole collection when stats["total"] is larger.
    caption = f"Showing {len(filtered)} of {len(tickets)} loaded tickets"
    if stats["total"] > len(tickets):
        caption += f" (most recent {len(tickets)} of {stats['total']} total)"
    st.caption(caption)

    if not filtered:
        st.info("No tickets match the current filters.")
        return

    # Summary table, sorted so the most urgent work surfaces first
    rows = [
        {
            "Ticket": t.get("ticket_id", ""),
            "Customer": t.get("user_name", ""),
            "Category": t.get("category", ""),
            "Priority": t.get("priority", ""),
            "Sentiment": t.get("sentiment", ""),
            "Status": t.get("status", ""),
            "Created": t.get("created_at"),
        }
        for t in filtered
    ]
    df = pd.DataFrame(rows)
    df["_rank"] = df["Priority"].map(Config.PRIORITY_LEVELS).fillna(99)
    df = df.sort_values(["_rank", "Created"], ascending=[True, False]).drop(columns="_rank")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### Ticket Detail")

    ids = [t.get("ticket_id", "") for t in filtered]
    selected_id = st.selectbox("Select a ticket", ids, key="q_selected")
    ticket = next((t for t in filtered if t.get("ticket_id") == selected_id), None)
    if not ticket:
        return

    dcol1, dcol2 = st.columns([2, 1])

    with dcol1:
        st.markdown(f"**Customer:** {ticket.get('user_name','')} "
                    f"<{ticket.get('user_email','')}>")
        lang = ticket.get("language", "en")
        st.markdown(f"**Language:** {get_language_name(lang)}")
        st.markdown("**Issue**")
        st.info(ticket.get("issue_description", ""))
        if ticket.get("summary"):
            st.markdown(f"**AI Summary:** {ticket['summary']}")
        st.markdown("**AI Response Sent to Customer**")
        st.success(ticket.get("ai_response", "") or "—")

        attempts = ticket.get("attempt_history") or []
        if attempts:
            with st.expander(f"Self-help attempts before escalation ({len(attempts)})"):
                for i, attempt in enumerate(attempts, 1):
                    st.write(f"{i}. {attempt}")

        if ticket.get("screenshot_path"):
            path = ticket["screenshot_path"]
            if os.path.exists(path):
                st.image(path, caption="Customer screenshot", width=420)
            else:
                st.caption(f"Screenshot recorded at {path} (file no longer on disk)")

    with dcol2:
        priority = ticket.get("priority", "medium")
        st.markdown(
            f"<span class='category-badge priority-{priority}'>{priority.upper()}</span>",
            unsafe_allow_html=True,
        )
        st.metric("Category", ticket.get("category", "—"))
        st.metric("Sentiment", str(ticket.get("sentiment", "—")).capitalize())
        st.metric("SLA", f"{Config.PRIORITY_SLA.get(priority, 24)} h")
        created = ticket.get("created_at")
        if created:
            st.caption(f"Created {created:%Y-%m-%d %H:%M} UTC"
                       if hasattr(created, "strftime") else f"Created {created}")

        st.divider()
        current = ticket.get("status", "open")
        options = list(STATUS_LABELS)
        new_status = st.selectbox(
            "Status",
            options,
            index=options.index(current) if current in options else 0,
            format_func=lambda s: STATUS_LABELS[s],
            key=f"status_{selected_id}",
        )
        if st.button("💾 Update Status", key=f"save_{selected_id}"):
            if new_status == current:
                st.info("Status unchanged.")
            else:
                try:
                    if db.update_ticket_status(selected_id, new_status):
                        st.success(f"{selected_id} → {STATUS_LABELS[new_status]}")
                        st.rerun()
                    else:
                        st.error(f"Ticket {selected_id} not found.")
                except Exception as e:
                    st.error(f"❌ Update failed: {e}")


def render_analysis_interface():
    """Render the ticket analysis interface"""
    st.subheader("📊 Ticket Analysis")
    
    query = st.text_area(
        "Enter ticket to analyze:",
        placeholder="Paste a customer support ticket here...",
        height=150,
        key="analysis_query"
    )
    
    if st.button("🔍 Analyze Ticket", key="analyze_btn"):
        if query:
            try:
                with st.spinner("Analyzing..."):
                    # Categorize
                    categorization = st.session_state.response_generator.categorize_ticket(query)

                    # Query analysis
                    analysis = st.session_state.rag_engine.analyze_query(query)
            except Exception as e:
                st.error(f"❌ Analysis failed: {e}")
                return

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### 📋 Ticket Classification")
                st.json(categorization)

            with col2:
                st.markdown("### 📈 Retrieval Analysis")
                if analysis['has_results']:
                    st.metric("Average Similarity", f"{analysis['avg_similarity']:.2%}")
                    st.metric("Suggested Category", analysis['suggested_category'])
                    
                    # Category distribution chart
                    if analysis['category_distribution']:
                        st.bar_chart(analysis['category_distribution'])
                else:
                    st.warning("No similar tickets found")


def render_sampling_interface():
    """Render the response sampling interface"""
    st.subheader("🔄 Response Sampling")
    st.markdown("Generate multiple response candidates and select the best one.")
    
    query = st.text_area(
        "Customer Query:",
        placeholder="Enter the customer query...",
        height=100,
        key="sampling_query"
    )
    
    num_responses = st.slider("Number of candidates", 2, 5, 3)
    
    if st.button("🎲 Generate Candidates", key="sample_btn"):
        if query:
            with st.spinner("Generating multiple responses..."):
                candidates = st.session_state.response_generator.generate_multiple_responses(
                    query, num_responses
                )
            
            st.markdown("### Response Candidates")
            
            for candidate in candidates:
                with st.expander(
                    f"Response #{candidate['id']} - {candidate['style'].capitalize()} "
                    f"(temp: {candidate['temperature']})"
                ):
                    st.write(candidate['text'])
                    
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        if st.button("✅ Select", key=f"select_{candidate['id']}"):
                            st.session_state.selected_response = candidate['text']
                            st.success("Response selected!")


def render_feedback_interface():
    """Render the feedback interface"""
    st.subheader("📝 Feedback & Improvement")
    
    # Feedback form
    st.markdown("### Submit Feedback")
    
    original_response = st.text_area(
        "Original Response:",
        placeholder="Paste the response you want to improve...",
        height=100,
        key="original_response"
    )
    
    feedback = st.text_area(
        "Your Feedback:",
        placeholder="What should be improved? Be specific...",
        height=100,
        key="feedback_text"
    )
    
    rating = st.slider("Rating (1-5)", 1, 5, 3)
    
    if st.button("🔄 Improve Response", key="improve_btn"):
        if original_response and feedback:
            with st.spinner("Improving response..."):
                result = st.session_state.feedback_loop.submit_feedback(
                    query="",
                    original_response=original_response,
                    feedback=feedback,
                    rating=rating
                )
            
            st.markdown("### ✨ Improved Response")
            st.success(result['improved_response'])
    
    st.divider()
    
    # Feedback history
    st.markdown("### 📜 Feedback History")
    history = st.session_state.feedback_loop.get_feedback_history() if st.session_state.feedback_loop else []
    
    if history:
        for i, record in enumerate(history, 1):
            with st.expander(f"Feedback #{i} (Rating: {record.get('rating', 'N/A')})"):
                st.write(f"**Original:** {str(record.get('original_response', ''))[:200]}...")
                st.write(f"**Feedback:** {record.get('feedback', '')}")
                st.write(f"**Improved:** {str(record.get('improved_response', ''))[:200]}...")
    else:
        st.info("No feedback submitted yet.")
    
    # Export button
    if history:
        if st.button("📥 Export Feedback"):
            try:
                path = st.session_state.feedback_loop.export_feedback("feedback_export.json")
                st.success(f"Feedback exported to {path}")
            except OSError as e:
                st.error(f"❌ Export failed: {e}")


def main():
    """Main application entry point"""
    initialize_session_state()
    render_sidebar()
    render_main_content()
    
    # Footer
    st.divider()
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
        🤖 AI Customer Support Agent | Powered by Google Gemini & FAISS | 
        Built with Streamlit
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
