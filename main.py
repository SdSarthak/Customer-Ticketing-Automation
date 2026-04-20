"""
Main script to initialize and run the Customer Support Agent
This script provides a CLI interface for setting up the system
"""

import os
import sys
import argparse

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.data_loader import DataLoader
from src.embeddings import GeminiEmbeddings
from src.vector_store import FAISSVectorStore
from src.rag_engine import RAGEngine
from src.response_generator import ResponseGenerator


def setup_environment():
    """Setup and validate environment"""
    print("=" * 60)
    print("🤖 Customer Support Agent - Setup")
    print("=" * 60)
    
    # Check for API key
    if not Config.GOOGLE_API_KEY:
        print("\n❌ Error: GOOGLE_API_KEY not found!")
        print("Please create a .env file with your Google API key:")
        print("  GOOGLE_API_KEY=your_api_key_here")
        print("\nGet your API key from: https://makersuite.google.com/app/apikey")
        return False
    
    print("✅ Google API Key configured")
    return True


def initialize_system(data_path: str = None, force_rebuild: bool = False):
    """
    Initialize the support system
    
    Args:
        data_path: Path to customer support data CSV
        force_rebuild: Whether to rebuild vector store even if it exists
    """
    data_path = data_path or Config.DATA_PATH
    vector_store_path = Config.VECTOR_STORE_PATH
    
    # Check if vector store already exists
    if os.path.exists(os.path.join(vector_store_path, "faiss_index.bin")) and not force_rebuild:
        print("\n📂 Vector store already exists.")
        print("Use --force-rebuild to recreate from data.")
        
        # Load existing
        print("\n🔄 Loading existing vector store...")
        rag_engine = RAGEngine()
        rag_engine.load_from_disk(vector_store_path)
        print(f"✅ Loaded {rag_engine.vector_store.get_stats()['total_documents']} documents")
        return rag_engine
    
    # Create new vector store
    print(f"\n📊 Loading data from: {data_path}")
    
    if not os.path.exists(data_path):
        print(f"❌ Data file not found: {data_path}")
        print("Please provide a valid CSV file path.")
        return None
    
    # Load and process data
    loader = DataLoader(data_path)
    loader.load_data()
    
    print("\n📈 Data Statistics:")
    stats = loader.get_statistics()
    print(f"  Total records: {stats['total_records']}")
    print(f"  Columns: {stats['columns']}")
    
    documents = loader.create_documents()
    
    # Initialize RAG engine
    print("\n🔄 Initializing RAG Engine...")
    rag_engine = RAGEngine()
    rag_engine.initialize_from_documents(documents)
    
    # Save vector store
    print(f"\n💾 Saving vector store to: {vector_store_path}")
    rag_engine.save_to_disk(vector_store_path)
    
    return rag_engine


def interactive_mode(rag_engine: RAGEngine):
    """
    Run interactive chat mode
    
    Args:
        rag_engine: Initialized RAGEngine instance
    """
    print("\n" + "=" * 60)
    print("💬 Interactive Support Mode")
    print("=" * 60)
    print("Type 'quit' to exit, 'help' for commands")
    print()
    
    # Initialize response generator
    generator = ResponseGenerator(rag_engine=rag_engine)
    
    while True:
        try:
            query = input("\n👤 Customer: ").strip()
            
            if not query:
                continue
            
            if query.lower() == 'quit':
                print("\n👋 Goodbye!")
                break
            
            if query.lower() == 'help':
                print("\nAvailable commands:")
                print("  quit     - Exit the program")
                print("  help     - Show this help message")
                print("  analyze  - Analyze a ticket in detail")
                print("  similar  - Find similar past tickets")
                continue
            
            if query.lower() == 'analyze':
                ticket = input("Enter ticket to analyze: ").strip()
                result = generator.generate_with_analysis(ticket)
                print(f"\n📋 Category: {result['categorization'].get('category', 'N/A')}")
                print(f"⚡ Priority: {result['categorization'].get('priority', 'N/A')}")
                print(f"😊 Sentiment: {result['categorization'].get('sentiment', 'N/A')}")
                print(f"\n🤖 Response:\n{result['response']}")
                continue
            
            if query.lower() == 'similar':
                ticket = input("Enter query to find similar tickets: ").strip()
                similar = rag_engine.get_similar_tickets(ticket, top_k=3)
                print(f"\n🔍 Found {len(similar)} similar tickets:")
                for i, t in enumerate(similar, 1):
                    print(f"\n  [{i}] Score: {t['similarity_score']:.2%}")
                    print(f"      Query: {t['instruction'][:100]}...")
                continue
            
            # Generate response
            print("\n🤔 Thinking...")
            response = generator.generate_response(query)
            print(f"\n🤖 Support Agent:\n{response}")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="AI Customer Support Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --setup                    # Initialize the system
  python main.py --interactive              # Run interactive mode
  python main.py --data path/to/data.csv    # Use custom data file
  python main.py --force-rebuild            # Rebuild vector store
  python main.py --streamlit                # Run Streamlit app
        """
    )
    
    parser.add_argument(
        "--setup", 
        action="store_true",
        help="Initialize/setup the system"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive chat mode"
    )
    parser.add_argument(
        "--data",
        type=str,
        help="Path to customer support data CSV"
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force rebuild of vector store"
    )
    parser.add_argument(
        "--streamlit",
        action="store_true",
        help="Launch Streamlit application"
    )
    
    args = parser.parse_args()
    
    # Validate environment
    if not setup_environment():
        sys.exit(1)
    
    # Launch Streamlit
    if args.streamlit:
        import subprocess
        print("\n🚀 Launching Streamlit application...")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])
        return
    
    # Initialize system
    rag_engine = initialize_system(
        data_path=args.data,
        force_rebuild=args.force_rebuild
    )
    
    if rag_engine is None:
        sys.exit(1)
    
    # Run interactive mode if requested
    if args.interactive:
        interactive_mode(rag_engine)
    else:
        print("\n✅ System initialized successfully!")
        print("\nNext steps:")
        print("  1. Run with --interactive for chat mode")
        print("  2. Run with --streamlit for web interface")
        print("  3. Run: streamlit run app.py")


if __name__ == "__main__":
    main()
