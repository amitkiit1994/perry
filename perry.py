import streamlit as st
import requests
import json
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from langchain_core.prompts import PromptTemplate
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain import hub
from langchain.agents import AgentExecutor, create_openai_tools_agent
import time
import pytesseract 

# Helper function to make API requests and log cURL requests
def make_request(url, method='GET', headers=None, data=None, form_data=False):
    """Helper function to make API requests and log cURL requests."""
    st.write(f"Request URL: {url}")
    st.write(f"Request Method: {method}")
    st.write(f"Request Headers: {headers}")
    st.write(f"Request Data: {data}")

    curl_command = f'curl -X {method} "{url}"'
    if headers:
        for key, value in headers.items():
            curl_command += f' -H "{key}: {value}"'
    if data:
        if form_data:
            for key, value in data.items():
                curl_command += f' --form \'{key}="{value}"\''
        else:
            curl_command += f' -d \'{data}\''
    st.write(f"cURL Command: {curl_command}")

    try:
        if method == 'POST':
            if form_data:
                response = requests.post(url, headers=headers, files=data)
            else:
                response = requests.post(url, headers=headers, json=data)
        else:
            response = requests.get(url, headers=headers, params=data)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP error occurred: {e}")
        st.error(f"Response status code: {response.status_code}")
        st.error(f"Response content: {response.content.decode()}")
        raise
    return response.json()

# Define each step as a function using the @tool decorator
@tool
def generate_code(curl_command: str) -> dict:
    """
    Generates a Gatling code snippet based on a curl command.
    """
    st.write("Generating Gatling code snippet")
    url = 'http://localhost:8083/api/v1/burst/generate?generator=gatling'
    headers = {'user': 'amitkumardas@gofynd.com'}
    form_data = {'codeGenRequest': (None, json.dumps({"request": curl_command}), 'application/json')}

    try:
        response = requests.post(url, headers=headers, files=form_data)
        response.raise_for_status()
        st.write("Successfully generated Gatling code snippet")
        return response.json()
    except requests.RequestException as e:
        st.error(f"Request failed: {e}")
        return {"error": "Network or server issue."}
    except ValueError:
        st.error("Failed to parse response JSON.")
        return {"error": "Failed to parse response JSON."}

@tool
def get_price_estimate(duration: int = 2000, pool_configs: dict = None) -> dict:
    """Get price estimate for the load test."""
    if pool_configs is None:
        pool_configs = {
            "noOfPods": 5,
            "cpu": {
                "request": "800m",
                "limit": "800m"
            },
            "memory": {
                "request": "600Mi",
                "limit": "600Mi"
            }
        }
    api_url = 'http://localhost:8083/api/v1/burst/priceEstimator'
    headers = {
        'Content-Type': 'application/json',
        'user': 'amitkumardas@gofynd.com'
    }
    data = {
        "duration": duration,
        "poolConfigs": pool_configs
    }
    return make_request(api_url, method='POST', headers=headers, data=data)

@tool
def start_gatling_test(script: str, injector_configs: dict, pool_configs: dict, simulation_class: str = "RegressTest") -> dict:
    """Start the Gatling load test."""
    api_url = 'http://localhost:8083/api/v1/burst/gatling/start'
    headers = {
        'Content-Type': 'application/json',
        'user': 'amitkumardas@gofynd.com'
    }
    data = {
        "repo": "",
        "simulationClass": simulation_class,
        "script": script,
        "injectorConfigs": injector_configs,
        "poolConfigs": pool_configs
    }
    return make_request(api_url, method='POST', headers=headers, data=data)

@tool
def get_test_status(test_id: str) -> dict:
    """Get the status of the running test."""
    api_url = f'http://localhost:8083/api/v1/burst/status?testId={test_id}'
    headers = {
        'Content-Type': 'application/json',
        'user': 'amitkumardas@gofynd.com'
    }
    return make_request(api_url, method='GET', headers=headers)

@tool
def generate_report(test_id: str) -> dict:
    """Generate the load test report."""
    api_url = f'http://localhost:8083/api/v1/burst/report?testId={test_id}&generator=gatling'
    headers = {
        'Content-Type': 'application/json',
        'user': 'amitkumardas@gofynd.com'
    }
    return make_request(api_url, method='GET', headers=headers)

@tool
def take_screenshot(url: str) -> Image:
    """Take a screenshot of the report."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920x1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    driver.get(url)
    screenshot = driver.get_screenshot_as_png()
    driver.quit()
    
    screenshot_image = Image.open(BytesIO(screenshot))
    return screenshot_image

# Define tools list
tools = [generate_code, get_price_estimate, start_gatling_test, get_test_status, generate_report, take_screenshot]

# Instantiate the ChatOpenAI model
llm = ChatOpenAI(model="gpt-4")

# Pull the prompt template
prompt_template = PromptTemplate(
    input_variables=["agent_scratchpad"],
    template="""
        You are Perry, an agent specialized in performing load tests on web applications.
        1. You will take a curl command from the user, or generate a curl command from an application URL.
        2. Then, you will use the curl command to generate a Gatling code snippet.
        3. You will ask the user how long they want to run the test and for how many users.
        4. You will use these inputs to configure the load test parameters.
        5. You will estimate the price to run the load test.
        6. You will start the Gatling load test.
        7. You will poll the status of the test until it is completed.
        8. You will generate a report for the completed test.
        9. You will analyze the generated report and provide a conclusion.

        Be friendly, informative, and concise when explaining each step to the user. Your current task is: {agent_scratchpad}
    """
)

# Create the agent and executor
agent = create_openai_tools_agent(llm, tools, prompt=prompt_template)
agent_executor = AgentExecutor(agent=agent, tools=tools)

# Streamlit Interface
st.title("Perry - Your Performance Tester")

# Inputs
user_input = st.text_input("Enter the application URL or cURL command")
num_users = st.number_input("Number of Users", min_value=1)
duration = st.number_input("Duration (seconds)", min_value=1)

if st.button("Run Performance Test"):
    # Step 1: Generate Code
    code_response = generate_code.invoke(user_input)
    st.write("Generated Code:", code_response)

    # Extract necessary parts from the response if available
    code_snippet = code_response.get("codeSnippet", "")
    
    # Step 2: Get Price Estimate
    pool_configs = {
        "noOfPods": 5,
        "cpu": {
            "request": "800m",
            "limit": "800m"
        },
        "memory": {
            "request": "600Mi",
            "limit": "600Mi"
        }
    }
    price_response = get_price_estimate.invoke({"duration": duration, "pool_configs": pool_configs})
    st.write("Price Estimate:", price_response)


    # Step 3: Start Gatling Test
    script = code_snippet.replace('.exec', 'exec')
    injector_configs = {
        "noOfUsersPerSec": num_users,
        "maxDuration": duration,
        "additionalProperties": {}
    }

    test_response = start_gatling_test.invoke({"script": script, "injector_configs": injector_configs, "pool_configs": pool_configs})
    st.write("Test Started:", test_response)
        
    test_id = test_response.get("testId")

    # Polling for test status
    status = ""
    while status != "completed":
        status_response = get_test_status.invoke({"test_id": test_id})
        status = status_response.get("status", "")
        st.write("Test Status:", status_response)
        if status != "completed":
            time.sleep(10)  # Wait for 10 seconds before polling again

    # Step 4: Generate Report
    report_response = generate_report.invoke({"test_id": test_id})
    report_link = report_response.get("reportLink")
    st.write("Report Link:", report_link)
    
    if report_link:
        screenshot = take_screenshot.invoke({"url": report_link})
        st.image(screenshot)
        st.write("Test Conclusion:")
        buffered = BytesIO()
        screenshot.save(buffered, format="PNG")
        img_bytes = buffered.getvalue()

        extracted_text = pytesseract.image_to_string(screenshot)
        
        # Generate a conclusion using the LLM
        prompt = f"Analyze the following test report and provide a conclusion:\n\n{extracted_text}"
        conclusion = llm(prompt).choices[0].text.strip()
        
        st.write(conclusion)
