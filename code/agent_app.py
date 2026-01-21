from dotenv import load_dotenv
load_dotenv() ## load all the environemnt variables

import streamlit as st
import os, json
import sqlite3
import google.generativeai as genai
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, Dict, Any

## Configure Genai Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = "gemini-2.5-flash"

class AppState(TypedDict):
    question: str
    intent: Optional[str]
    sql: Optional[str]
    summary_sql: Optional[Dict[str, str]]
    results: Optional[Any]
    summary_results: Optional[Any]
    final_answer: Optional[str]
    error: Optional[str]

## Function To Load Google Gemini Model and provide queries as response
def get_gemini_response(question,prompt,model):
    model=genai.GenerativeModel(model)
    response=model.generate_content([prompt[0],question])
    return response.text

## Function To retrieve query from the database
def read_sql_query(sql,db):
    print(sql)
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

def intent_agent(state: AppState):
    intent = detect_intent(state["question"], model)
    return {"intent": intent}

def adhoc_sql_agent(state: AppState):
    sql = get_gemini_response(
        state["question"],
        adhoc_prompt,
        model
    )
    return {"sql": sql}

def summary_planner_agent(state: AppState):
    text = get_gemini_response(
        state["question"],
        summary_prompt,
        model
    )
    parsed = safe_json_loads(text)
    if not parsed:
        return {"error": "Invalid summary JSON"}
    return {"summary_sql": parsed["queries"]}

def validation_agent(state: AppState):
    if state.get("sql") and not validation_query(state["sql"]):
        return {"error": "Unsafe SQL detected"}
    if state.get("summary_sql"):
        for sql in state["summary_sql"].values():
            if not validation_query(sql):
                return {"error": "Unsafe SQL detected in summary queries"}
    return {}

def adhoc_execution_agent(state: AppState):
    if state.get("sql"):
        results = read_sql_query(state["sql"], "sales.db")
        return {"results": results}
    return {}

def summary_execution_agent(state: AppState):
    if state.get("summary_sql"):
        results = execute_summary_queries(
            {"queries": state["summary_sql"]},
            "sales.db"
        )
        return {"summary_results": results}
    return {}

def insight_agent(state: AppState):
    if state.get("intent") == "SUMMARY":
        summary = generate_summary_insight(
            state["summary_results"],
            model
        )
        return {"final_answer": summary}
    return state

def route_intent(state: AppState):
    if state["intent"] == "FACT_SQL":
        return "adhoc_sql"
    elif state["intent"] == "SUMMARY":
        return "summary_plan"
    else:
        return END

graph = StateGraph(AppState)

graph.add_node("intent", intent_agent)
graph.add_node("adhoc_sql", adhoc_sql_agent)
graph.add_node("summary_plan", summary_planner_agent)
graph.add_node("validate", validation_agent)
graph.add_node("adhoc_execute", adhoc_execution_agent)
graph.add_node("summary_execute", summary_execution_agent)
graph.add_node("insight", insight_agent)

graph.set_entry_point("intent")

graph.add_conditional_edges(
    "intent",
    route_intent,
    {
        "adhoc_sql": "adhoc_sql",
        "summary_plan": "summary_plan",
        END: END
    }
)

graph.add_edge("adhoc_sql", "validate")
graph.add_edge("validate", "adhoc_execute")
graph.add_edge("adhoc_execute", END)

graph.add_edge("summary_plan", "validate")
graph.add_edge("validate", "summary_execute")
graph.add_edge("summary_execute", "insight")
graph.add_edge("insight", END)

app = graph.compile()
app.get_graph().draw_png("retail_assistant_agentgraph.png")

## Streamlit App
st.set_page_config(page_title="App to answer retail queries")
st.header("Retail Assistant")

question=st.text_input("Input: ",key="input")

submit=st.button("Ask the question")

if submit:
    state = {
        "question": question,
        "intent": None,
        "sql": None,
        "summary_sql": None,
        "results": None,
        "final_answer": None,
        "error": None
    }

    final_state = app.invoke(state)

    if final_state.get("error"):
        st.error(final_state["error"])
    else:
        st.success("Answer")
        if final_state["intent"] == "FACT_SQL":
            st.write(final_state.get("results"))
        elif final_state["intent"] == "SUMMARY":
            st.write(final_state.get("final_answer"))