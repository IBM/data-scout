# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

PROMPT_TEMPLATES = {
    "query": (
        'Can you come up with Google searches that I can perform to look-up different aspects of information related to the following user query: {input}.'
        'List the searches using markdown symbol + and enclose in double quotes.'
        'Do not group queries and just provide a single list.'
    ),
    "topic": '''
        Given a topic, your task is to break it down into well-defined subtopics that are commonly associated with it. The topic that you are given may be derived from a parent topic.
        Each subtopic should be concise, non-overlapping, and commonly recognized in academic or practical contexts.
        List the subtopics using markdown symbol + and enclose in double quotes.
        Do not group subtopics and just provide a single list.
        Do not include explanations—only the subtopics.
        \n
        Topic Tree:
        {context}
        \n
        Current Topic: {input}
    ''',
    "expand": '''
        Your task is to generate a list of Google search queries that will surface a broad range of documents useful for pre-training or teaching a model about the specified topic.
        If the topic is a sub-topic of another subject, a "topic tree" will be supplied to give context.

        Topic
        {input}

        Topic Tree
        {context}

        Guidelines
        1. Produce 10–12 distinct queries.
        2. Each query should be written exactly as it would appear in the Google search bar (use single quotation marks only for exact-phrase matching if desired).
        3. Present the queries in a markdown list, each line beginning with + and the query surrounded by double quotes.
        ''',
    "keyword": '''
        Can you come up with a list of keywords that could be used to retrieve documents related to {input}?
        List the subtopics using markdown symbol + and enclose in double quotes.
        Do not group subtopics and just provide a single list.
        Do not include explanations—only the subtopics.
        ''',

    "crawlable_annotation": '''
        You are an information-filtering assistant.  For each of the following domains, produce one JSON object per line in this exact format:

        {{
        "domain": "<domain>",
        "reason": "<one-sentence justification>",
        "status": "<OK | Copyright-heavy | Adult | Spam>"
        }}

        *Do not add any surrounding text or commentary.*
        If a domain does not fit into the four buckets, choose the most appropriate one and explain it in the reason field.

        **Rules for classification**

        - **OK** – No obvious paywall, no adult content, not known spam.
        - **Copyright-heavy** – Major news outlets, scholarly publishers, large media companies that serve copyrighted material (e.g., nytimes.com, cnn.com).
        - **Adult** – Primary purpose is erotic or pornographic content; contains X-rated tags.
        - **Spam** – Low-quality sites frequently change domains, host malware, phishing, or are known for spam.
        - **Social-media** - Social media sites

        {input}
        ''',
    "relevancy_annotation": '''
        I want you to help me figure out whether a document that I downloaded from the internet is relevant for a user's data need or topic. Answer with one JSON object and only use Yes or No. Do not provide an explanation or anything else. I am going to share a snippet of that document's text with you.

        USER DATA NEED/TOPIC:
        {input}

        TEXT:
        {text}

        ANSWER:
        {{
        "relevant": "Yes | No"
        }}
        ''',
    "sub_category_annotation": '''
        I want you to help me classify the sub-category of a document, with reference to the user's data need or topic. Answer with one JSON object and only mention the sub-category or None. Do not provide an explanation or anything else. I am going to share a snippet of that document's text with you, possible sub-categories, and the user input/data need.

        USER DATA NEED/TOPIC:
        {input}

        SUB_CATEGORIES:
        {sub_categories}

        TEXT:
        {text}

        ANSWER:
        {{
        "sub_category": "<sub_category> | None"
        }}
        '''
    }
