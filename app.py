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
from src.embeddings import GeminiEmbeddings
from src.vector_store import FAISSVectorStore
from src.rag_engine import RAGEngine
from src.response_generator import ResponseGenerator, FeedbackLoop


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


def load_system(data_path: str = None):
    """Load and initialize the support system"""
    try:
        with st.spinner("🔄 Initializing AI Support System..."):
            # Check for API key
            if not Config.GOOGLE_API_KEY:
                st.error("❌ Google API Key not found. Please set GOOGLE_API_KEY in .env file")
                return False
            
            # Check if vector store exists
            vector_store_path = Config.VECTOR_STORE_PATH
            
            if os.path.exists(os.path.join(vector_store_path, "faiss_index.bin")):
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
            
            # Initialize response generator
            response_generator = ResponseGenerator(rag_engine=rag_engine)
            feedback_loop = FeedbackLoop(response_generator)
            
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


def process_uploaded_file(uploaded_file):
    """Process an uploaded CSV file"""
    try:
        # Save uploaded file
        data_dir = "data"
        os.makedirs(data_dir, exist_ok=True)
        file_path = os.path.join(data_dir, "customer_support_tickets.csv")
        
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        st.session_state.data_loaded = True
        return file_path
        
    except Exception as e:
        st.error(f"❌ Error processing file: {str(e)}")
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
                load_system(file_path)
    
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
    tab1, tab2, tab3, tab4 = st.tabs([
        "💬 Support Chat", 
        "📊 Ticket Analysis", 
        "🔄 Response Sampling",
        "📝 Feedback & History"
    ])
    
    # Tab 1: Support Chat
    with tab1:
        render_chat_interface()
    
    # Tab 2: Ticket Analysis
    with tab2:
        render_analysis_interface()
    
    # Tab 3: Response Sampling
    with tab3:
        render_sampling_interface()
    
    # Tab 4: Feedback History
    with tab4:
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
        with st.spinner("🤔 Analyzing query and generating response..."):
            # Get complete analysis
            result = st.session_state.response_generator.generate_with_analysis(user_query)
            st.session_state.current_response = result
            
            # Store in chat history
            st.session_state.chat_history.append({
                "query": user_query,
                "result": result
            })
    
    # Display current response
    if st.session_state.current_response:
        result = st.session_state.current_response
        
        # Categorization badges
        cat = result.get('categorization', {})
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Category", cat.get('category', 'N/A'))
        with col2:
            priority = cat.get('priority', 'medium')
            st.metric("Priority", priority.upper())
        with col3:
            st.metric("Sentiment", cat.get('sentiment', 'neutral').capitalize())
        with col4:
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
            with st.spinner("Analyzing..."):
                # Categorize
                categorization = st.session_state.response_generator.categorize_ticket(query)
                
                # Query analysis
                analysis = st.session_state.rag_engine.analyze_query(query)
                
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
                st.write(f"**Original:** {record['original_response'][:200]}...")
                st.write(f"**Feedback:** {record['feedback']}")
                st.write(f"**Improved:** {record['improved_response'][:200]}...")
    else:
        st.info("No feedback submitted yet.")
    
    # Export button
    if history:
        if st.button("📥 Export Feedback"):
            st.session_state.feedback_loop.export_feedback("feedback_export.json")
            st.success("Feedback exported to feedback_export.json")


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
