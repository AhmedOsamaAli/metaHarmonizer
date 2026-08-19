workspace "MetaHarmonizer" "Curator-in-the-loop clinical-metadata harmonization platform (C4 model, reverse-engineered from source)." {

    !identifiers hierarchical

    model {
        curator = person "Curator / Admin" "Uploads studies, reviews mappings, exports cBioPortal data."
        agent   = person "LLM Agent" "Claude / Cursor calling harmonization tools over MCP."

        gemini  = softwareSystem "Google Gemini API" "Stage-4 LLM column matching (optional)." "External"
        vocab   = softwareSystem "NCI EVS / OLS / UMLS" "Biomedical vocabulary lookups (cached)." "External"
        resend  = softwareSystem "Resend" "Transactional email (verify / reset)." "External"
        hibp    = softwareSystem "HaveIBeenPwned" "Breached-password check (fail-open)." "External"
        sentry  = softwareSystem "Sentry" "Error tracking (optional)." "External"
        hf      = softwareSystem "HuggingFace Hub" "Embedding-model source (seeded offline)." "External"
        cbio    = softwareSystem "cBioPortal" "Downstream import target for harmonized exports." "External"

        mh = softwareSystem "MetaHarmonizer Dashboard" "Automated metadata harmonization with human review and reproducibility pins." {
            spa    = container "Web SPA" "Curator dashboard UI." "React 18, Vite, TypeScript, Tailwind, React Query" "Web"
            caddy  = container "Caddy Reverse Proxy" "Serves SPA static assets, fronts /api + WebSocket, CSP + TLS." "Caddy 2" "Proxy"

            api = container "API Service" "REST + WebSocket; authz, orchestration, middleware." "FastAPI, uvicorn, Pydantic" {
                routers = component "Routers" "HTTP: auth, admin, harmonize, mappings, ontology, quality, export, federation, audit, ws, health." "FastAPI APIRouter"
                middleware = component "Middleware chain" "Request-id + error envelope, security headers, Prometheus, rate-limit + idempotency, CORS." "ASGI middleware"
                services = component "Domain Services" "harmonizer, exporter, analytics, active_learning, learned_apply, linkml_gate, schema_diff, federation." "Python"
                repos = component "Repositories" "All SQL/ORM access per aggregate." "SQLAlchemy async"
                adapter = component "Engine Adapter" "EngineProtocol + MetaHarmonizerAdapter/Mock; only importer of the engine." "Python Protocol"
                core = component "Core" "settings, logging, metrics, limits, jobs (Redis bus), storage, security." "Python"
            }

            worker = container "Job Worker" "Runs harmonize jobs + cron (retention, nightly labeled export)." "arq (Redis)" {
                task = component "run_harmonize" "Shared harmonize task (inline + queue)." "Python/anyio"
                cron = component "Cron jobs" "Nightly labeled export; retention sweeps." "arq cron"
                wadapter = component "Engine Adapter (worker)" "Same EngineProtocol boundary." "Python Protocol"
            }

            engine = container "Harmonization Engine" "SchemaMapEngine (4-stage cascade) + OntoMapEngine + KnowledgeDb." "metaharmonizer 0.4.1, SentenceTransformers, FAISS, SQLite" "Engine"
            mcp    = container "MCP Server" "3 tools (harmonize_table/columns/values) for LLM agents." "Python FastMCP (stdio/SSE)"

            pg     = container "PostgreSQL" "System of record: studies, mappings(+versions), ontology mappings, audit, users, pins, jobs." "PostgreSQL 16 (asyncpg)" "Database"
            redis  = container "Redis" "Job queue, progress pub/sub, rate-limit, idempotency, WS tickets, cancel flags." "Redis 7" "Cache"
            objstore = container "Object Store" "Uploaded CSVs + generated exports." "file:// volume or S3/R2" "Storage"
            kb     = container "Knowledge Base" "FAISS indexes + embedding model + ontology corpora (seeded bundle)." "FAISS + models + CSV corpora" "Storage"
        }

        # People -> system
        curator -> mh.spa "Uses" "HTTPS"
        agent -> mh.mcp "Calls tools" "MCP stdio/SSE"

        # Edge + SPA
        mh.spa -> mh.caddy "Loads assets / API calls" "HTTPS"
        mh.caddy -> mh.api "Proxies /api, /healthz, /metrics, WS" "HTTP/WS"
        mh.caddy -> mh.spa "Serves static SPA (web_dist)" "HTTPS"

        # API internal wiring
        mh.api.routers -> mh.api.middleware "Wrapped by"
        mh.api.routers -> mh.api.services "Invokes"
        mh.api.services -> mh.api.repos "Reads/writes via"
        mh.api.services -> mh.api.adapter "Calls engine via"
        mh.api.repos -> mh.pg "SQL" "asyncpg"
        mh.api.core -> mh.redis "Rate-limit, idempotency, progress bus" "RESP"
        mh.api.adapter -> mh.engine "Harmonize / map values"
        mh.api -> mh.objstore "Stores uploads / exports"

        # Jobs
        mh.api -> mh.redis "Enqueue harmonize (queue mode)" "arq"
        mh.redis -> mh.worker "Dequeue job" "arq"
        mh.worker.task -> mh.worker.wadapter "Runs engine via"
        mh.worker.wadapter -> mh.engine "Harmonize / map values"
        mh.worker -> mh.pg "Persist mappings + pins" "asyncpg"
        mh.worker -> mh.objstore "Reads upload"
        mh.worker -> mh.redis "Publish progress"

        # Engine dependencies
        mh.engine -> mh.kb "Vector search + term lookup"
        mh.engine -> gemini "Stage-4 LLM (optional)" "HTTPS"
        mh.engine -> vocab "Vocabulary lookups (cached)" "HTTPS"
        mh.engine -> hf "Loads model (offline in prod)" "HTTPS"

        # MCP reuses the engine
        mh.mcp -> mh.engine "Harmonize via adapter boundary"

        # External app integrations
        mh.api -> resend "Sends verify/reset email" "HTTPS"
        mh.api -> hibp "Breach check on signup" "HTTPS"
        mh.api -> sentry "Reports errors" "HTTPS"
        curator -> cbio "Imports harmonized export"

        deploymentEnvironment "Production" {
            deploymentNode "Internet" {
                curatorBrowser = deploymentNode "Browser" "" "Chrome/Edge/Firefox" {
                    containerInstance mh.spa
                }
            }
            deploymentNode "Docker Host / VM" "" "Linux + Docker Compose" {
                deploymentNode "caddy" "" "Caddy 2 (TLS)" {
                    containerInstance mh.caddy
                }
                deploymentNode "api (1..N)" "" "uvicorn" {
                    containerInstance mh.api
                }
                deploymentNode "worker (1..N)" "" "arq" {
                    containerInstance mh.worker
                    containerInstance mh.engine
                }
                deploymentNode "postgres" "" "PostgreSQL 16" {
                    containerInstance mh.pg
                }
                deploymentNode "redis" "" "Redis 7" {
                    containerInstance mh.redis
                }
                deploymentNode "volumes" "" "Docker named volumes" {
                    containerInstance mh.objstore
                    containerInstance mh.kb
                }
            }
        }
    }

    views {
        systemContext mh "SystemContext" {
            include *
            autolayout lr
        }
        container mh "Containers" {
            include *
            autolayout lr
        }
        component mh.api "API-Components" {
            include *
            autolayout lr
        }
        deployment mh "Production" "Deployment" {
            include *
            autolayout lr
        }

        styles {
            element "Person" {
                shape Person
                background #4338ca
                color #ffffff
            }
            element "External" {
                background #94a3b8
                color #ffffff
            }
            element "Web" {
                shape WebBrowser
                background #1d4ed8
                color #ffffff
            }
            element "Proxy" {
                shape Hexagon
                background #a21caf
                color #ffffff
            }
            element "Database" {
                shape Cylinder
                background #15803d
                color #ffffff
            }
            element "Cache" {
                shape Cylinder
                background #b91c1c
                color #ffffff
            }
            element "Storage" {
                shape Folder
                background #ca8a04
                color #ffffff
            }
            element "Engine" {
                background #6d28d9
                color #ffffff
            }
            element "Container" {
                background #2563eb
                color #ffffff
            }
            element "Component" {
                background #dbeafe
                color #0b2a5b
            }
        }
    }
}
