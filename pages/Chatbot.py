import streamlit as st
from langchain.chains import ConversationalRetrievalChain
from qdrant_client import QdrantClient
from base_agent import BaseAgent
import time
import random
from utils import *

from dotenv import load_dotenv
load_dotenv() # Load our environment variables

# Function to show the username popup
def username_popup():
    st.title("Welcome!")
    st.write("Please enter your Domino username to continue.")
    username = st.text_input("Enter your username", key="username_input")

    if username:
        st.session_state.user = username
        st.rerun()
    else:
        st.error("Username cannot be empty.")

agent = BaseAgent()

q_client = QdrantClient(url=os.environ["QDRANT_URL"],
                        api_key=os.environ["QDRANT_KEY"])

st.set_page_config(page_title="👩‍🔬🔬💬 BioRAG Analyser")
st.title('👩‍🔬🔬💬 BioRAG Analyser')


# Check if the username is set, otherwise show the popup
if "user" not in st.session_state:
    username_popup()
else:

    use_case_df = get_use_case_dataframe(st.session_state.user)

    if "use_cases" not in st.session_state.keys():
        st.session_state['use_cases'] = use_case_df['Use Case Name'].tolist()
    else:
        st.session_state['use_cases'] = use_case_df['Use Case Name'].tolist()


    if len(use_case_df) > 0:
        # Add a sidebar with a dropdown menu and document names
        st.sidebar.title("Select a Use Case")
        selected_use_case = st.sidebar.selectbox("Choose a use case 👇:", st.session_state['use_cases'])

        vectordb_documents = Qdrant(q_client, f"{st.session_state.user}_{selected_use_case}_documents", agent.embeddings)

        st.sidebar.write("The documents being analysed are:")
        for document_name_sb in get_document_names(use_case_df, selected_use_case):
            st.sidebar.write(f"📑 {document_name_sb}")
        # Display the selected use case
        st.write(f"Always double check important info.")

            
        # Initialize or load chat history
        if "messages" not in st.session_state.keys():
            st.session_state.messages = get_chat_history(st.session_state.user, selected_use_case)
        else:
            st.session_state.messages = get_chat_history(st.session_state.user, selected_use_case)


        # Sidebar with a button to delete chat history
        with st.sidebar:
            if st.button("Delete Chat History"):
                st.session_state.messages = []
                update_chat_history([], st.session_state.user, selected_use_case)


        # Display chat messages
        for message in st.session_state.messages: # May need to alter to not show system message
            avatar = "🧑" if message["role"] == "user" else "👩‍🔬"
            with st.chat_message(message["role"], avatar=avatar):
                st.markdown(message["content"])


        # Main chat interface
        if prompt := st.chat_input("Please enter your question"):
            retrieval_chat_history = convert_chat_history(st.session_state.messages)
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar="🧑"):
                st.markdown(prompt)

            with st.chat_message("assistant", avatar="👩‍🔬"):
                message_placeholder = st.empty()
                full_response = ""

                with st.spinner("Smart assistant is thinking..."):
                    qa_chain = ConversationalRetrievalChain.from_llm(
                        llm=agent.model,
                        retriever=vectordb_documents.as_retriever(
                            search_kwargs={"k": 20, "score_threshold": 0.6}
                        ),
                        condense_question_prompt=summarization_prompt,
                        combine_docs_chain_kwargs={"prompt": qa_prompt},
                        return_source_documents=True,
                        verbose=True
                    )

                    answer_bundle = qa_chain({"question": prompt, 
                                            "chat_history": retrieval_chat_history, 
                                            "n_documents": len(get_document_names(use_case_df, selected_use_case))})
                
                response = answer_bundle["answer"]
                source_documents = answer_bundle["source_documents"]
                source_names = extract_source_names(source_documents)
                response += f"\n\nSources:\n" + "\n".join(f"- {name}" for name in source_names)
                
                # Simulate typing effect
                for char in response.split(" "):
                    full_response += f" {char} "
                    message_placeholder.markdown(full_response + " | ")
                    time.sleep(round(random.uniform(0.015, 0.2), 3)) 

                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})


                # Save chat history after each interaction
                update_chat_history(st.session_state.messages, st.session_state.user, selected_use_case)

    else:
        st.warning("⚠️You have no use cases! Please create one in the use cases tab")
