from qdrant_client import QdrantClient
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Qdrant
import re
import os
import pickle
from base_agent import BaseAgent
from langchain.prompts import PromptTemplate
import pandas as pd
from docx import Document
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError


# Define our text splitter
text_splitter = RecursiveCharacterTextSplitter(
chunk_size=1000,
chunk_overlap=100,
length_function=len,
is_separator_regex=False)


# Initialise our Qdrant client to store vectors
qdrant_client = QdrantClient(
    url=os.environ["QDRANT_URL"], 
    api_key=os.environ["QDRANT_KEY"],
)

# Initialise Base agent for embeddings
agent = BaseAgent()
embeddings = agent.embeddings


template_summarization = """
Create a valid prompt using the user input "{question}" for GPT 4o.

-----
Expand the prompt for GPT-4o with the following chat history only in case the input and the history mention the same specific topic, otherwise do not add the history.
{chat_history}
-----

The prompt must ask to GPT to: 
- use only the information contained in the document 
- never add information from the GPT background knowledge 
- the answer must be in the same language of the question
- explicitly tell to GPT-4o to answer in English.

"""

template = """ 
You are a useful and precise assistant.
You receive in input the question: {question}.
The documents below refers to {n_documents} data sources.
You receive in input the following documents: {context}.

Answer the question in English.

Question: {question}
Answer:
"""


# initialize prompt for summarization
summarization_prompt = PromptTemplate(
    template=template_summarization,
    input_variables=["chat_history", "question"],
)

# initialize prompt for summarization
qa_prompt = PromptTemplate(
    template=template,
    input_variables=["question", "context", "n_documents"],
)


def clean_texts(input_text):
    text = re.sub(r'\s+', ' ', input_text)
    return text


def extract_source_names(source_documents):
    return set([doc.metadata.get("source", "Unknown Source") for doc in source_documents])


def extract_text_from_pdf(pdf_doc):
    """
    Extracts and cleans text from a PDF document.

    This function iterates over all pages of the given PDF document, extracts text, 
    replaces newlines with spaces, removes non-alphanumeric characters (excluding 
    spaces, commas, periods, and percentage signs), and condenses multiple spaces 
    into a single space. The cleaned text from all pages is concatenated into a 
    single string.

    Args:
        pdf_doc (PdfDocument): A PDF document object containing pages to be processed.

    Returns:
        str: The concatenated and cleaned text extracted from the PDF document.
    """
    all_text = ''
    for page in pdf_doc.pages:
        # Extract text from the page
        page_text = page.extract_text()
        page_text = page_text.replace("\n", " ")
        page_text = re.sub(r"[^a-zA-Z0-9 ,.%]", " ", page_text)
        page_text = re.sub("\s+", " ", page_text)
        if page_text:  # Check if there's text on the page
            all_text += page_text + ' '  # Append text with a newline
    return all_text


def text_to_docs(input_text):
    """
    Splits the input text into chunks and extracts the text content from each chunk.

    This function uses a text splitter to divide the input text into manageable chunks,
    and then extracts and returns the text content from each chunk.

    Args:
        input_text (str): The input text to be split into chunks.

    Returns:
        list of str: A list containing the text content of each chunk.
    """
    docs = text_splitter.create_documents([input_text]) # Split the text into chunks
    docs = [page.page_content for page in docs] # Extract only the text from each document object
    return docs


def extract_text_from_docx(file):
    """Extract text from a DOCX file."""
    doc = Document(file)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text += cell.text + "\t"
            text += "\n"
    return text


def remove_duplicate_documents(documents):
    """
    Removes duplicate documents from a list of document objects.

    This function iterates through a list of documents, identifies duplicates based on the 
    content and source metadata, and returns a list of unique documents.

    Args:
        documents (list of Document): A list of document objects, where each document has 
                                      a `page_content` attribute and `metadata` dictionary 
                                      containing a 'source' key.

    Returns:
        list of Document: A list containing only the unique document objects from the input list.
    """
    seen = set()
    unique_docs = []
    
    for doc in documents:
        doc_tuple = (doc.page_content, doc.metadata['source'])
        if doc_tuple not in seen:
            seen.add(doc_tuple)
            unique_docs.append(doc)
    
    return unique_docs


def docs_to_vectordb(docs, collection_name):
    """
    Uploads documents to a Qdrant vector database collection specific to the user.

    This function takes a list of document objects and a username, and uploads the documents 
    to a Qdrant vector database collection named after the username. It uses the Qdrant API 
    and handles any exceptions that occur during the process.

    Args:
        docs (list of Document): A list of document objects to be uploaded.
        collection_name (str): The collection name to create a specific collection for the documents.

    Returns:
        Qdrant or bool: Returns the Qdrant instance if successful, otherwise returns False.
    """
    try:
        qdrant = Qdrant.from_documents(
            documents=docs,
            embedding=agent.embeddings,
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_KEY"],
            collection_name=f"{collection_name}_documents",
            force_recreate=True
        )
    except Exception as e:
        print(f"Something went wrong: {e}")
        qdrant = False

    return qdrant


def upload_to_azure_blob(file_path):
    """
    Uploads a file to an Azure Blob Storage container.

    This function uploads a specified file to a designated Azure Blob Storage container using 
    the connection string and container name provided in environment variables. It handles any 
    exceptions that occur during the upload process.

    Args:
        file_path (str): The local path to the file that needs to be uploaded.
    """
    blob_service_client = BlobServiceClient.from_connection_string(os.environ["AZURE_BLOB_CONNECTION_STRING"])
    blob_client = blob_service_client.get_blob_client(container=os.environ["AZURE_BLOB_CONTAINER_NAME"], blob=file_path)
    try:
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
    except Exception as e:
        print(f"Exception occurred: {e}")


def get_azure_blob(azure_blob_path):
    """
    Downloads a blob from Azure Blob Storage, deserializes it using pickle, and returns the object.

    This function downloads a specified blob from an Azure Blob Storage container using the 
    connection string and container name provided in environment variables. It saves the blob 
    locally, deserializes it using pickle, and returns the deserialized object. The local file 
    is removed after deserialization. If an error occurs, the local file is removed and an empty 
    list is returned.

    Args:
        azure_blob_path (str): The path (name) of the blob in Azure Blob Storage to be downloaded.

    Returns:
        object: The deserialized object from the blob. If an error occurs, returns an empty list.

    """
    blob_service_client = BlobServiceClient.from_connection_string(os.environ["AZURE_BLOB_CONNECTION_STRING"])
    blob_client = blob_service_client.get_blob_client(container=os.environ["AZURE_BLOB_CONTAINER_NAME"], blob=azure_blob_path)
    try:
        with open(azure_blob_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())
        
        with open(azure_blob_path, 'rb') as file:
            # Load the object from the file
            azure_blob = pickle.load(file)

        os.remove(azure_blob_path)
    except Exception as e:
        os.remove(azure_blob_path)
        azure_blob = []
    return azure_blob
    

def delete_azure_blob(azure_blob_path):
    """
    Deletes a specified blob from an Azure Blob Storage container.

    This function deletes a specified blob from an Azure Blob Storage container using the 
    connection string and container name provided in environment variables. If the blob 
    does not exist, the function will pass silently.

    Args:
        azure_blob_path (str): The path (name) of the blob in Azure Blob Storage to be deleted.
    """
    blob_service_client = BlobServiceClient.from_connection_string(os.environ["AZURE_BLOB_CONNECTION_STRING"])
    blob_client = blob_service_client.get_blob_client(container=os.environ["AZURE_BLOB_CONTAINER_NAME"], blob=azure_blob_path)
    try:
        blob_client.delete_blob()
    except ResourceNotFoundError as e:
        pass


def get_use_case_dataframe(user_id):
    """
    Downloads and loads a user's use case dataframe from Azure Blob Storage.

    This function retrieves a pickled pandas DataFrame from an Azure Blob Storage container 
    based on the provided user ID. If the DataFrame cannot be retrieved, it returns an empty 
    DataFrame with specified columns.

    Args:
        user_id (str): The ID of the user whose use case DataFrame is to be retrieved.

    Returns:
        pd.DataFrame: A pandas DataFrame containing the user's use cases. If retrieval fails, 
                      returns an empty DataFrame with columns 'Use Case Name' and 'Use Case Documents'.
    """
    user_use_cases_df_file_path = f"{user_id}_use_cases_df.pkl"
    blob_service_client = BlobServiceClient.from_connection_string(os.environ["AZURE_BLOB_CONNECTION_STRING"])
    blob_client = blob_service_client.get_blob_client(container=os.environ["AZURE_BLOB_CONTAINER_NAME"], blob=user_use_cases_df_file_path)
    
    try:
        # Download the blob to a file
        with open(user_use_cases_df_file_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())
        uc_df = pd.read_pickle(user_use_cases_df_file_path)
        os.remove(user_use_cases_df_file_path)
    
    except Exception as e:
        try:
            os.remove(user_use_cases_df_file_path)
        except Exception as _e:
            pass
        uc_df = pd.DataFrame(columns=['Use Case Name', 'Use Case Documents'])
    
    return uc_df


def add_use_case(user_id, new_use_case_name, document_names):
    """
    Adds a new use case to the user's use case DataFrame and uploads it to Azure Blob Storage.

    This function retrieves the user's use case DataFrame from Azure Blob Storage, adds a new 
    use case with the specified name and associated documents, and then uploads the updated 
    DataFrame back to Azure Blob Storage.

    Args:
        user_id (str): The ID of the user whose use case DataFrame is to be updated.
        new_use_case_name (str): The name of the new use case to be added.
        document_names (list of str): A list of document names associated with the new use case.

    Returns:
        None
    """
    new_row = {"Use Case Name": new_use_case_name, "Use Case Documents": ", ".join(document_names)}
    temp_df = get_use_case_dataframe(user_id)
    temp_df.loc[len(temp_df)] = new_row
    temp_df.to_pickle(f"{user_id}_use_cases_df.pkl")
    upload_to_azure_blob(f"{user_id}_use_cases_df.pkl")
    os.remove(f"{user_id}_use_cases_df.pkl")


def delete_use_case(user_id, deletion_use_case_name):
    """
    Deletes a specified use case from the user's use case DataFrame and updates Azure Blob Storage.

    This function retrieves the user's use case DataFrame from Azure Blob Storage, removes the 
    specified use case, updates the DataFrame, and uploads it back to Azure Blob Storage. Additionally, 
    it deletes the associated collection in Qdrant and removes the corresponding chat history from Azure Blob Storage.

    Args:
        user_id (str): The ID of the user whose use case is to be deleted.
        deletion_use_case_name (str): The name of the use case to be deleted.

    Returns:
        None
    """
    temp_df = get_use_case_dataframe(user_id)
    temp_df = temp_df[temp_df["Use Case Name"] != deletion_use_case_name]
    temp_df.reset_index(drop=True, inplace=True)
    temp_df.to_pickle(f"{user_id}_use_cases_df.pkl")
    upload_to_azure_blob(f"{user_id}_use_cases_df.pkl")
    os.remove(f"{user_id}_use_cases_df.pkl")
    qdrant_client.delete_collection(f"{user_id}_{deletion_use_case_name}_documents")
    delete_azure_blob(f"{user_id}_{deletion_use_case_name}_chat_history.pkl")
    

def get_chat_history(user_id, use_case_id):
    """
    Retrieves the chat history for a specific use case from Azure Blob Storage.

    This function downloads and deserializes the chat history for a given user and use case 
    from Azure Blob Storage. The chat history is stored in a pickle file with a naming 
    convention based on the user ID and use case ID.

    Args:
        user_id (str): The ID of the user whose chat history is to be retrieved.
        use_case_id (str): The ID of the use case for which the chat history is to be retrieved.

    Returns:
        object: The deserialized chat history object. If retrieval fails, an empty list is returned.
    """
    user_chat_history = get_azure_blob(f"{user_id}_{use_case_id}_chat_history.pkl")
    return user_chat_history


def update_chat_history(chat_messages, user_id, use_case_id):
    """
    Updates the chat history for a specific use case and uploads it to Azure Blob Storage.

    This function serializes the given chat messages and saves them to a local pickle file. 
    It then uploads the pickle file to Azure Blob Storage and removes the local file.

    Args:
        chat_messages (list): A list of chat messages to be saved.
        user_id (str): The ID of the user whose chat history is to be updated.
        use_case_id (str): The ID of the use case for which the chat history is to be updated.

    Returns:
        None
    """
    chat_history_path = f"{user_id}_{use_case_id}_chat_history.pkl"
    with open(chat_history_path, 'wb') as file:
        pickle.dump(chat_messages, file)
    upload_to_azure_blob(chat_history_path)
    os.remove(chat_history_path)


def get_document_names(use_cases_main_df, use_case_name):
    """
    Retrieves the document names associated with a specific use case from the main DataFrame.

    This function searches the provided DataFrame for the specified use case name and returns 
    a list of document names associated with that use case.

    Args:
        use_cases_main_df (pd.DataFrame): The main DataFrame containing use case information, 
                                          including use case names and associated documents.
        use_case_name (str): The name of the use case for which to retrieve document names.

    Returns:
        list of str: A list of document names associated with the specified use case.
    """
    return use_cases_main_df[use_cases_main_df['Use Case Name']==use_case_name]['Use Case Documents'].tolist()[0].split(', ')


def convert_chat_history(role_user_chat):
    """
    Converts a list of chat messages into a list of tuples pairing user and response messages.

    This function takes a list of chat messages, where each message is a dictionary with a 
    "content" key, and converts it into a list of tuples. Each tuple contains a pair of messages 
    (user message, response message). If the number of messages is odd, the last user message is 
    paired with an empty string.

    Args:
        role_user_chat (list of dict): A list of chat messages, where each message is a dictionary 
                                       containing a "content" key with the message text.

    Returns:
        list of tuple: A list of tuples, where each tuple contains a user message and a response 
                       message.
    """
    converted_history = []
    for i in range(0, len(role_user_chat), 2):
        if i + 1 < len(role_user_chat):
            converted_history.append((role_user_chat[i]["content"], role_user_chat[i + 1]["content"]))
        else:
            # In case there's an odd number of messages, pair the last user message with an empty string
            converted_history.append((role_user_chat[i]["content"], ""))
    return converted_history[-5:]
