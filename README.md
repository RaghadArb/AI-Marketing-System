# AI Marketing System

An AI-powered digital marketing platform developed as a Master's project using Django.

The system provides a unified environment for managing companies, products, and marketing campaigns while integrating Artificial Intelligence for marketing strategy generation, content creation, advertising poster generation, customer support, customer voice analysis, and campaign performance analysis.

---

## Project Overview

The AI Marketing System is designed to support Marketing Specialists in managing digital marketing activities from a single platform.

The system combines traditional campaign management with Generative AI, Retrieval-Augmented Generation (RAG), semantic search, and marketing analytics to assist with content creation, customer support, campaign analysis, and decision-making.

---

## Main Features

### 1. Authentication and Role Management
- Secure user authentication.
- Role-based access control.
- Marketing Specialist dashboard.
- Dashboard Admin for managing user accounts and access.

### 2. Company Management
- Create, view, update, and manage companies.
- Store company information and branding data.
- Each company's data is isolated and associated with its own marketing resources.

### 3. Product Management
- Manage products associated with companies.
- Store product descriptions and images.
- Use product information when preparing marketing campaigns and AI-generated content.

### 4. Campaign Management
- Create and manage marketing campaigns.
- Associate campaigns with companies and products.
- Define platform, budget, dates, status, and campaign information.
- Track campaign performance.

### 5. AI Marketing Strategy Generation
- Generate marketing strategies based on company, product, and campaign information.
- Uses Generative AI and structured prompt engineering.
- Provides AI-generated strategic suggestions to support campaign planning.

### 6. AI Marketing Content Generation
- Generate marketing content for different platforms.
- Produces multiple content suggestions for each request.
- Content generation considers company, product, campaign, platform, and marketing context.
- Supports platform-specific marketing communication.

### 7. AI Advertising Poster Generation
- Generate advertising visuals based on campaign information and creative briefs.
- Integrates AI image-generation services.
- Supports automated poster generation as part of the campaign workflow.

### 8. Knowledge Base Management
- Upload and manage company-specific knowledge documents.
- Documents are processed and divided into text chunks.
- Knowledge is indexed for semantic retrieval.
- Each company maintains its own knowledge context.

### 9. AI Customer Support with RAG
- Public customer-support interface for each company.
- Uses Retrieval-Augmented Generation (RAG).
- Retrieves relevant information from the company's Knowledge Base before generating responses.
- Stores customer-support conversations and messages.

### 10. Customer Voice Analysis
- Analyzes customer-support conversations.
- Extracts useful insights from customer interactions.
- Helps the Marketing Specialist understand customer concerns, needs, and recurring topics.

### 11. Campaign Performance Analytics
- Stores and analyzes campaign performance metrics.
- Supports metrics such as:
  - Impressions
  - Clicks
  - CTR
  - Conversions
  - Cost
  - Revenue
  - ROI
- Provides charts and performance summaries.

### 12. AI Campaign Analysis and Recommendations
- Combines deterministic campaign metrics with AI interpretation.
- Analyzes campaign performance.
- Generates recommendations and marketing insights to support decision-making.

### 13. Reports and Executive Dashboard
- Central Marketing Specialist dashboard.
- Campaign performance summaries.
- Customer-support analytics.
- Marketing insights.
- Charts and reports.
- Unified view of the platform's marketing activities.

---

## AI Architecture

The platform combines several AI techniques:

### Generative AI
Large Language Models are used for:
- Marketing strategy generation
- Marketing content generation
- Customer-support responses
- Campaign interpretation and recommendations
- Customer voice analysis

### Prompt Engineering
Structured prompts provide the AI models with relevant company, product, campaign, platform, and performance context.

### Retrieval-Augmented Generation (RAG)

The customer-support component uses a RAG pipeline:

1. Company documents are uploaded to the Knowledge Base.
2. Text is extracted from each document.
3. Documents are divided into chunks.
4. Sentence Transformers generate vector embeddings.
5. Embeddings are stored in ChromaDB.
6. A customer question is converted into an embedding.
7. Relevant knowledge chunks are retrieved using semantic similarity.
8. Retrieved context is provided to the language model.
9. The model generates a context-aware response.

---

## Technology Stack

### Backend
- Python
- Django 5
- Django ORM

### Frontend
- HTML
- CSS
- Bootstrap 5
- Django Templates

### Database
- MySQL

### Artificial Intelligence
- Large Language Models (LLMs)
- Prompt Engineering
- Retrieval-Augmented Generation (RAG)
- Sentence Transformers
- AI image generation

### Vector Database
- ChromaDB

### Production Deployment
- Ubuntu Linux
- Gunicorn
- Nginx
- MySQL

---

## Database Structure

The main system entities include:

- User
- User Profile
- Company
- Product
- Campaign
- Campaign Content
- Campaign Performance
- Knowledge Document
- Support Conversation
- Support Message

The relational application data is stored in MySQL, while ChromaDB is used separately for vector embeddings and semantic retrieval.

---

## AI Evaluation

The AI components were evaluated separately using controlled evaluation datasets and dedicated metrics.

### Customer Support / RAG

| Metric | Result |
|---|---:|
| Answer Accuracy | 88.0% |
| Faithfulness | 97.0% |
| Answer Relevance | 95.6% |
| Retrieval Hit Rate | 88.0% |
| Hallucination Rate | 4.0% |

### Marketing Content Generation

| Metric | Result |
|---|---:|
| Relevance | 94.6% |
| Factual Consistency | 86.2% |
| Platform Appropriateness | 99.2% |
| Language Quality | 96.9% |
| CTA Quality | 83.1% |
| Overall Score | 92.0% |

### Advertising Image Generation

| Metric | Result |
|---|---:|
| Relevance | 100.0% |
| Campaign Alignment | 93.3% |
| Visual Quality | 88.9% |
| Text & Brand Quality | 51.1% |
| Usability | 77.8% |
| Overall Score | 82.2% |

---

## Functional Testing

The system was evaluated through functional and automated testing.

- Functional test cases: **18 / 18 passed**
- Automated tests: **100 / 101 passed**

The remaining automated test was related to an evaluation-template validation case rather than a failure of a core operational system function.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/RaghadArb/AI-Marketing-System.git
cd AI-Marketing-System
