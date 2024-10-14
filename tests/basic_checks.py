import unittest
import os
import importlib.util

class TestOpenAIQA(unittest.TestCase):

    def test_library_langchain_installed(self):
        """ Test if langchain library is installed """
        langchain_installed = importlib.util.find_spec("langchain") is not None
        self.assertTrue(langchain_installed, "langchain library is not installed")
        
    def test_library_pandas_installed(self):
        """ Test if pandas library is installed """
        pandas_installed = importlib.util.find_spec("pandas") is not None
        self.assertTrue(pandas_installed, "pandas library is not installed")
        
    def test_library_openai_installed(self):
        """ Test if openai library is installed """
        openai_installed = importlib.util.find_spec("openai") is not None
        self.assertTrue(openai_installed, "openai library is not installed")
        
    def test_library_pdfplumber_installed(self):
        """ Test if pdfplumber library is installed """
        pdfplumber_installed = importlib.util.find_spec("pdfplumber") is not None
        self.assertTrue(pdfplumber_installed, "pdfplumber library is not installed")
        
    def test_library_streamlit_installed(self):
        """ Test if streamlit library is installed """
        streamlit_installed = importlib.util.find_spec("streamlit") is not None
        self.assertTrue(streamlit_installed, "streamlit library is not installed")
        
    def test_library_azure_installed(self):
        """ Test if azure library is installed """
        azure_installed = importlib.util.find_spec("azure") is not None
        self.assertTrue(azure_installed, "azure library is not installed")

    def test_library_qdrant_client_exists(self):
        """ Test if qdrant-client library is installed """
        qdrant_client_installed = importlib.util.find_spec("qdrant") is not None
        self.assertTrue(qdrant_client_installed, "qdrant-client library is not installed")

if __name__ == '__main__':
    unittest.main()
