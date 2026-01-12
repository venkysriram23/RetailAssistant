from dotenv import load_dotenv
load_dotenv() ## load all the environemnt variables

import streamlit as st
import os, json
import sqlite3
import google.generativeai as genai

## Configure Genai Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

## Function To Load Google Gemini Model and provide queries as response
def get_gemini_response(question,prompt,model):
    model=genai.GenerativeModel(model)
    response=model.generate_content([prompt[0],question])
    return response.text

## Fucntion To retrieve query from the database
def read_sql_query(sql,db):
    conn=sqlite3.connect(db)
    cur=conn.cursor()
    cur.execute(sql)
    rows=cur.fetchall()
    conn.commit()
    conn.close()
    for row in rows:
        print(row)
    return rows

def detect_intent(question, model):
    intent_prompt = f"""
    Classify the user query into ONE of the following:
    1. FACT_SQL - needs a single SQL query
    2. SUMMARY - needs an analytical summary

    Return only one word.

    Query: {question}
    """
    model = genai.GenerativeModel(model)
    response = model.generate_content(intent_prompt)
    return response.text.strip()

# Function to execute summary queries
def execute_summary_queries(summary_sql_json, db):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    results = {}
    for key, sql in summary_sql_json["queries"].items():
        if validation_query(sql):
            cursor.execute(sql)
            results[key] = cursor.fetchall()

    conn.close()
    return results

# Define Summary Prompt
summary_prompt = [
    """
    SYSTEM MESSAGE (STRICT INSTRUCTIONS):
    You are NOT a chat assistant.
    You are an automated SQL generation agent.

    DATA CONTEXT:
    The sales data ALREADY EXISTS in a SQLite database sales and has the following columns - index, Order ID, Date,
    Status,	Fulfilment,	Sales Channel, ship-service-level, Style, SKU, Category, Size, ASIN, Courier Status,
    Qty, currency, Amount, ship-city, ship-state, ship-postal-code, ship-country, promotion-ids, B2B, fulfilled-by,	Unnamed: 22 

    You MUST NOT:
    - Ask for files
    - Ask for data
    - Explain anything
    - Respond in natural language

    TASK:
    Generate SQL queries required to create an EXECUTIVE SALES SUMMARY.

    The summary must cover:
    1. Overall performance
    2. Revenue by region (ship_state)
    3. Revenue by category
    4. Top products by revenue
    5. Fulfilment performance comparison

    OUTPUT FORMAT (STRICT JSON ONLY):
    {
    "queries": {
        "overall_metrics": "SQL",
        "revenue_by_state": "SQL",
        "revenue_by_category": "SQL",
        "top_products": "SQL",
        "fulfilment_split": "SQL"
    }
    }

    RULES:
    - Table name must be `sales`
    - Use SUM(amount) for revenue
    - Use COUNT(DISTINCT Order ID) for orders
    - Use GROUP BY where required
    - Do NOT include explanations
    - Do NOT ask for data
    - Do NOT use markdown
    - Output must be valid JSON only

    EXAMPLE OUTPUT:
    {
    "queries": {
        "overall_metrics":
        "SELECT SUM(amount) AS total_revenue,
                COUNT(DISTINCT Order ID) AS total_orders,
                SUM(qty) AS total_units
        FROM sales",

        "revenue_by_state":
        "SELECT ship_state, SUM(amount) AS revenue
        FROM sales
        GROUP BY ship_state
        ORDER BY revenue DESC",

        "revenue_by_category":
        "SELECT category, SUM(amount) AS revenue
        FROM sales
        GROUP BY category
        ORDER BY revenue DESC",

        "top_products":
        "SELECT sku, SUM(amount) AS revenue
        FROM sales
        GROUP BY sku
        ORDER BY revenue DESC
        LIMIT 5",

        "fulfilment_split":
        "SELECT fulfilment, SUM(amount) AS revenue
        FROM sales
        GROUP BY fulfilment"
    }
    }
    """
]

## Define ad-hoc query Prompt
adhoc_prompt=[
    """
    You are an expert in converting English questions to SQL query!
    The SQL database has the name sales and has the following columns - index, Order ID, Date,
    Status,	Fulfilment,	Sales Channel, ship-service-level, Style, SKU, Category, Size, ASIN, Courier Status,
    Qty, currency, Amount, ship-city, ship-state, ship-postal-code, ship-country, promotion-ids, B2B, fulfilled-by,	Unnamed: 22 
    \n\nFor example,\nExample 1 - How many entries of records are present?, 
    the SQL command will be something like this SELECT COUNT(*) FROM sales;
    \nExample 2 - Tell me all the sales in Mumbai city?, 
    the SQL command will be something like this SELECT * FROM sales 
    where ship-city="Mumbai"; 
    also the sql code should not have ``` in beginning or end and sql word in output
    """
]

def generate_summary_insight(summary_results, model):
    insight_prompt = f"""
    You are a retail executive assistant.

    Given the following aggregated sales data, generate a concise business summary.
    Highlight:
    - Overall performance
    - Regional trends
    - Category insights
    - Any anomalies

    Data:
    {summary_results}
    """
    model = genai.GenerativeModel(model)
    response = model.generate_content(insight_prompt)
    return response.text

def safe_json_loads(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def validation_query(sql):
    FORBIDDEN_KEYWORDS = [
        "DROP", "DELETE", "UPDATE", "INSERT",
        "ALTER", "TRUNCATE", "ATTACH", "DETACH"
    ]

    sql_upper = sql.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_upper:
            return False

    return True


## Streamlit App
st.set_page_config(page_title="App to answer retail queries")
st.header("Retail Assistant")

question=st.text_input("Input: ",key="input")

submit=st.button("Ask the question")

# if submit is clicked
if submit:
    model='gemini-3-flash-preview'
    try:
        intent = detect_intent(question, model)

        if intent == "FACT_SQL":
            response=get_gemini_response(question,adhoc_prompt,model)
            print(response)
            if validation_query(response):
                response=read_sql_query(response,"sales.db")
                st.subheader("The Response is")
                for row in response:
                    print(row)
                    st.header(row)  

        elif intent == "SUMMARY":
            summary_sql_text = get_gemini_response(
                question,
                summary_prompt,
                model
            )
            print(summary_sql_text)
            summary_sql_json = safe_json_loads(summary_sql_text)
            summary_results = execute_summary_queries(
                summary_sql_json,
                "sales.db"
            )

            summary_text = generate_summary_insight(
                summary_results,
                model
            )

            st.subheader("Executive Summary")
            st.write(summary_text)    
    except Exception as e:
        st.subheader("issue in processing the request: "+str(e))