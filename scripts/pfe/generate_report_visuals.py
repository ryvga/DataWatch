from __future__ import annotations

import subprocess
from pathlib import Path
from datetime import date
from html import escape


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/diagrams/pfe"
SOURCE_DIR = OUT / "mermaid"

INIT = """%%{init: {'theme':'base','themeVariables':{'fontFamily':'Arial','primaryColor':'#F7F3F2','primaryTextColor':'#171717','primaryBorderColor':'#B4232F','lineColor':'#5B6068','secondaryColor':'#F3F4F6','tertiaryColor':'#FFFFFF','clusterBkg':'#FFFFFF','clusterBorder':'#D1D5DB','actorBkg':'#FFFFFF','actorBorder':'#B4232F','actorTextColor':'#171717','signalColor':'#404040','signalTextColor':'#171717','noteBkgColor':'#FFF7ED','noteBorderColor':'#C2410C','noteTextColor':'#171717'}}}%%
"""

DIAGRAMS = {
    "gantt": INIT + """gantt
    title Planification du PFE et continuité du produit
    dateFormat YYYY-MM-DD
    axisFormat %d %b
    tickInterval 1week
    excludes weekends
    section Cadrage
    Analyse du besoin et état de l'art        :done, a1, 2026-06-01, 12d
    Architecture et socle multi-tenant       :done, a2, 2026-06-08, 16d
    section Produit
    Sources, découverte et profilage          :done, b1, 2026-06-18, 20d
    Détection hybride et incidents            :done, b2, 2026-07-01, 20d
    Narration IA et alertes                    :done, b3, 2026-07-13, 18d
    Moniteurs typés et collaboration          :done, b4, 2026-07-24, 22d
    Gouvernance IA observe-only               :done, b5, 2026-08-04, 18d
    section Validation
    Tests, correction et durcissement         :done, c1, 2026-08-10, 15d
    Seed, captures et parcours de démonstration :done, c2, 2026-08-20, 9d
    Rapport et préparation de soutenance      :crit, c3, 2026-08-17, 15d
    Fin de la période PFE                      :milestone, m1, 2026-08-31, 0d
    section Après le PFE
    Évolution produit et validation terrain   :active, d1, 2026-09-01, 21d
""",
    "use_cases": INIT + """flowchart LR
    op["Opérateur data"]
    admin["Administrateur d'organisation"]
    staff["Personnel Panopta"]
    subgraph DW[Panopta]
      observe([Observer la qualité])
      configure([Configurer la surveillance])
      respond([Traiter un incident])
      govern([Gouverner les systèmes IA])
      operate([Administrer la plateforme])
    end
    op --> observe & respond & govern
    admin --> observe & configure & respond & govern
    staff --> operate
    style DW fill:#fff,stroke:#B4232F,stroke-width:2px
""",
    "use_cases_workspace": INIT + """flowchart LR
    op["Opérateur data"]
    owner["Owner / Admin"]
    subgraph OBS[Observation et intervention]
      dash([Consulter Operations])
      table([Explorer profils et contrôles])
      monitor([Valider puis activer un moniteur DSL])
      incident([Ouvrir un incident P1 P2 P3])
      ai([Lire causes probables et requêtes])
      action([Affecter, acquitter ou résoudre])
      report([Générer un rapport de santé])
    end
    subgraph CFG[Configuration de l'espace]
      source([Créer et tester une source])
      team([Gérer membres, équipes et astreintes])
      alert([Configurer e-mail Slack PagerDuty])
      prefs([Régler les préférences individuelles])
      gov([Déclarer un système IA et ses preuves])
    end
    op --> dash & table & monitor & incident & ai & action & report
    owner --> source & team & alert & prefs & gov
    incident -. inclut .-> ai
    incident -. prolonge .-> action
""",
    "use_cases_staff": INIT + """flowchart LR
    staff["Administrateur Panopta"]
    subgraph PORTAL[Portail staff isolé]
      login([Se connecter avec un compte staff])
      stats([Consulter les statistiques globales])
      orgs([Filtrer et ouvrir une organisation])
      plan([Changer l'offre ou l'abonnement])
      users([Activer et gérer les rôles])
      keys([Gérer clé LLM et clé API])
      staffusers([Administrer les comptes staff])
    end
    staff --> login --> stats
    staff --> orgs --> plan
    orgs --> users & keys
    staff --> staffusers
""",
    "sequence_source": INIT + """sequenceDiagram
    autonumber
    actor Admin
    participant UI as Interface React
    participant API as API FastAPI
    participant Crypto as Service de chiffrement
    participant Conn as Connecteur
    participant DB as PostgreSQL Panopta
    Admin->>UI: Renseigne le type et les paramètres
    UI->>API: POST /sources
    API->>Crypto: Chiffrer par clé dérivée de org_id
    Crypto-->>API: Configuration Fernet
    API->>DB: Persister la source
    Admin->>UI: Tester la connexion
    UI->>API: POST /sources/{id}/test
    API->>Crypto: Déchiffrer dans le tenant courant
    API->>Conn: Ouvrir une connexion en lecture
    Conn-->>API: Capacités et état
    API-->>UI: connected
    Admin->>UI: Découvrir puis sélectionner une table
    UI->>API: POST /tables
    API->>DB: Inscrire la table et la planification
    API-->>UI: Table surveillée
""",
    "sequence_monitoring": INIT + """sequenceDiagram
    autonumber
    participant S as APScheduler
    participant W as Worker Celery
    participant C as Connecteur source
    participant P as ProfilerService
    participant A as AnomalyService
    participant I as IncidentService
    participant DB as PostgreSQL
    S->>W: profile_table(table_id)
    W->>C: Requête agrégée unique
    C-->>P: Métriques et schéma
    P->>DB: Enregistrer TableProfile
    W->>A: run_anomaly_checks
    A->>DB: Lire historique et configuration
    A->>A: Règles + z-score + IsoForest + STL
    A->>DB: Enregistrer CheckResults
    A->>I: Regrouper les échecs
    I->>DB: Créer ou enrichir l'incident ouvert
    I-->>W: incident_id
""",
    "sequence_investigation": INIT + """sequenceDiagram
    autonumber
    actor Op as Opérateur
    participant UI as Interface incident
    participant API as API incidents
    participant LLM as Narration IA
    participant DB as PostgreSQL
    participant Alert as E-mail Slack PagerDuty
    API->>LLM: Contexte minimal structuré P1 P2
    LLM-->>API: Résumé, hypothèses, actions, requêtes
    API->>DB: Enregistrer la narration JSON
    API->>Alert: Router selon sévérité et table
    Alert-->>Op: Notification
    Op->>UI: Ouvrir l'incident
    UI->>API: GET /incidents/{id}
    API-->>UI: Faits, signaux, narration et chronologie
    Op->>UI: Affecter à Data Engineering
    UI->>API: PATCH assignee / team
    Op->>UI: Acquitter
    UI->>API: PATCH status=acknowledged
    API->>DB: Horodater auteur et transition
""",
    "sequence_ai_governance": INIT + """sequenceDiagram
    autonumber
    actor Owner as Responsable IA
    participant UI as AI Governance
    participant API as API gouvernance
    participant DB as Ledger PostgreSQL
    participant Eval as Évaluateur de contrôles
    participant Alerts as Routage incidents
    Owner->>UI: Enregistrer système, usages et responsables
    UI->>API: Créer version et déclaration
    API->>DB: Écrire des révisions immuables
    Owner->>UI: Activer un manifeste
    UI->>API: Comparer puis activer par CAS
    API->>DB: Lier manifeste et déploiement
    API->>Eval: Évaluer preuves valides à la date de coupure
    Eval->>DB: Écrire preuve et résultat typé
    alt contrôle non satisfait
      Eval->>DB: Dédupliquer un incident de gouvernance
      Eval->>Alerts: Émettre un signal observe-only
    end
    API-->>UI: Statut, raisons, confiance et risque résiduel
    Note over UI,Alerts: Aucun blocage automatique ni certificat de conformité
""",
    "activity_incident": INIT + """flowchart TD
    start((Début)) --> detect[Exécuter les contrôles]
    detect --> failed{Au moins un échec ?}
    failed -- Non --> clean[Aucun incident] --> finish((Fin))
    failed -- Oui --> open[Incident ouvert]
    open --> dedupe[Ajouter le signal au même incident]
    dedupe --> open
    open --> triage[Prendre en charge et investiguer]
    open --> mute[Mettre temporairement en sourdine]
    mute -->|fin de la période| open
    triage --> decision{Conclusion de l'enquête}
    decision -->|impact confirmé| ack[Acquitter]
    decision -->|preuve contraire| falsep[Classer faux positif]
    ack --> recovered{Métriques revenues à la normale ?}
    recovered -- Non --> triage
    recovered -- Oui --> resolved[Résoudre] --> finish
    falsep --> finish
    resolved -. anomalie distincte .-> reopened[Réouvrir]
    style failed fill:#FFF7ED,stroke:#C2410C
    style decision fill:#FFF7ED,stroke:#C2410C
    style recovered fill:#FFF7ED,stroke:#C2410C
""",
    "architecture": INIT + """flowchart TB
    U[Utilisateurs workspace et staff]
    subgraph PRESENTATION[Couche présentation]
      React[SPA React Vite]
      Admin[Portail staff séparé]
    end
    subgraph API[Couche application]
      FastAPI[API FastAPI et contrats]
      Auth[JWT, clés API et isolation tenant]
      Scheduler[APScheduler]
    end
    subgraph DOMAIN[Couche métier]
      Profile[Profilage]
      Detect[Détection hybride]
      Incident[Incidents]
      Narration[Narration IA]
      Governance[Gouvernance IA observe-only]
      Alerts[Alertes et collaboration]
    end
    subgraph ASYNC[Couche asynchrone]
      Celery[Workers Celery]
      Redis[(Redis)]
    end
    subgraph DATA[Couche données et intégrations]
      PG[(PostgreSQL 16)]
      Connectors[Registre de connecteurs]
      Sources[(Sources clientes)]
      Providers[OpenRouter, SMTP, Slack, PagerDuty]
    end
    U --> React & Admin
    React & Admin --> FastAPI
    FastAPI --> Auth & Scheduler & DOMAIN
    Scheduler --> Celery
    Celery <--> Redis
    Celery --> Profile --> Connectors --> Sources
    Profile --> Detect --> Incident --> Narration --> Alerts
    Governance --> Alerts
    DOMAIN --> PG
    Narration & Alerts --> Providers
""",
    "deployment": INIT + """flowchart LR
    Browser["Navigateur\nacme-corp.localhost"]
    subgraph DOCKER[Machine de démonstration Docker Compose]
      FE["frontend\nNginx + React"]
      API["api\nFastAPI"]
      Worker["worker\nCelery"]
      Redis[("redis\nfile et cache")]
      Meta[("postgres\n29 tables métier")]
      Mail["mailhog\nSMTP + boîte web"]
      Acme[("acme-db\ndonnées métier")]
      Analytics[("analytics-db\nsecond tenant")]
    end
    Browser -->|HTTP 5173| FE
    FE -->|/api 8000| API
    API --> Meta & Redis
    API --> Worker
    Worker --> Redis & Meta & Acme & Analytics
    Worker -->|SMTP 1025| Mail
    Browser -. démonstration alertes .-> Mail
""",
    "classes_monitoring": INIT + """classDiagram
    class Organization {+UUID id;+string slug;+string plan}
    class DataSource {+UUID id;+string type;+json connection_config;+string status}
    class MonitoredTable {+UUID id;+string schema_name;+string table_name;+float sensitivity;+json check_config}
    class TableProfile {+UUID id;+bigint row_count;+float freshness_seconds;+json column_metrics;+json provenance}
    class CheckResult {+UUID id;+string check_type;+string status;+float deviation_score}
    class Incident {+UUID id;+string severity;+string status;+json fired_checks;+json llm_narration}
    class AlertConfig {+UUID id;+string channel;+json config;+bool is_active}
    Organization "1" *-- "0..*" DataSource
    DataSource "1" *-- "0..*" MonitoredTable
    MonitoredTable "1" *-- "0..*" TableProfile
    TableProfile "1" *-- "0..*" CheckResult
    MonitoredTable "1" *-- "0..*" Incident
    MonitoredTable "1" o-- "0..*" AlertConfig
""",
    "classes_collaboration": INIT + """classDiagram
    class Organization {+UUID id;+string slug}
    class User {+UUID id;+string email;+string role;+bool is_active}
    class Invite {+UUID id;+string role;+datetime expires_at}
    class Team {+UUID id;+string name;+string color}
    class TeamMember {+UUID id;+string role;+datetime joined_at}
    class OncallSchedule {+datetime starts_at;+datetime ends_at}
    class NotificationPrefs {+bool notify_assigned;+bool daily_digest;+int digest_hour}
    class ApiKey {+UUID id;+string name;+string key_hash}
    Organization "1" *-- "0..*" User
    Organization "1" *-- "0..*" Invite
    Organization "1" *-- "0..*" Team
    Organization "1" *-- "0..*" ApiKey
    Team "1" *-- "0..*" TeamMember
    User "1" -- "0..*" TeamMember
    Team "1" *-- "0..*" OncallSchedule
    User "1" -- "0..1" NotificationPrefs
""",
    "classes_monitors": INIT + """classDiagram
    class MonitoredTable {+UUID id;+json check_config;+json autopilot}
    class CustomMonitor {+UUID id;+string sql_query;+string severity;+json last_result}
    class Monitor {+UUID id;+string name;+string mode;+string status;+int current_revision}
    class MonitorRevision {+UUID id;+int revision;+json definition;+string definition_hash;+string schema_fingerprint}
    class MonitorRun {+UUID id;+string idempotency_key;+string trigger_type;+string status;+json measurements;+json result}
    class EvaluationState {+string phase;+int breach_streak;+int recovery_streak;+datetime cooldown_until;+int version}
    MonitoredTable "1" *-- "0..*" CustomMonitor
    MonitoredTable "1" *-- "0..*" Monitor
    Monitor "1" *-- "1..*" MonitorRevision
    Monitor "1" *-- "0..*" MonitorRun
    MonitorRevision "1" -- "0..*" MonitorRun
    Monitor "1" *-- "0..1" EvaluationState
""",
    "classes_ai_governance": INIT + """classDiagram
    class AISystem {+UUID id;+string lifecycle_status;+string autonomy_level;+json risk_context}
    class AISystemVersion {+int version_number;+string definition_hash;+string model}
    class AIDataUseRevision {+string use_kind;+list fields;+string schema_fingerprint;+string evidence_class}
    class AIReleaseManifest {+string manifest_hash;+datetime evidence_cutoff}
    class AIDeployment {+string environment;+string status;+int activation_generation}
    class AIApproval {+string reviewer_role;+string decision;+string evidence_snapshot_hash}
    class AIEvidence {+string evidence_type;+string content_hash;+string redaction_class}
    class AIControlEvaluation {+string control_id;+string status;+string reason_code;+string input_hash}
    class AIGovernanceIncident {+string control_id;+string severity;+string status;+string dedupe_key}
    AISystem "1" *-- "1..*" AISystemVersion
    AISystemVersion "1" *-- "0..*" AIDataUseRevision
    AISystemVersion "1" *-- "0..*" AIReleaseManifest
    AISystem "1" *-- "0..*" AIDeployment
    AIReleaseManifest "1" -- "0..*" AIApproval
    AIDeployment "1" *-- "0..*" AIEvidence
    AIEvidence "0..1" -- "0..*" AIControlEvaluation
    AIControlEvaluation "1" -- "0..1" AIGovernanceIncident
""",
    "erd_overview": INIT + """flowchart TB
    subgraph ID[Identité et collaboration - 9 tables]
      organizations --> users & api_keys & invites & teams
      teams --> team_members & oncall_schedules
      users --> team_members & user_notification_prefs
      staff_users
    end
    subgraph MON[Surveillance - 7 tables]
      organizations --> data_sources --> monitored_tables
      monitored_tables --> table_profiles & incidents & alert_configs & custom_monitors
      table_profiles --> check_results
    end
    subgraph DSL[Moniteurs typés - 4 tables]
      monitored_tables --> monitors --> monitor_revisions
      monitors --> monitor_runs & monitor_evaluation_states
      monitor_revisions --> monitor_runs
    end
    subgraph GOV[Gouvernance IA - 9 tables]
      organizations --> ai_systems --> ai_system_versions
      ai_system_versions --> ai_data_use_revisions & ai_release_manifests
      ai_systems --> ai_deployments
      ai_release_manifests --> ai_approvals
      ai_deployments --> ai_evidence
      ai_evidence --> ai_control_evaluations --> ai_governance_incidents
    end
    incidents -. affectation .-> users & teams
    ai_data_use_revisions -. source et table déclarées .-> data_sources & monitored_tables
    ai_evidence -. profil source optionnel .-> table_profiles
""",
    "erd_core": INIT + """erDiagram
    organizations ||--o{ data_sources : owns
    data_sources ||--o{ monitored_tables : exposes
    monitored_tables ||--o{ table_profiles : produces
    table_profiles ||--o{ check_results : evaluates
    monitored_tables ||--o{ incidents : triggers
    monitored_tables ||--o{ alert_configs : routes
    monitored_tables ||--o{ custom_monitors : runs
    monitored_tables ||--o{ monitors : defines
    monitors ||--o{ monitor_revisions : versions
    monitors ||--o{ monitor_runs : executes
    monitor_revisions ||--o{ monitor_runs : pins
    monitors ||--o| monitor_evaluation_states : tracks
    organizations {
      uuid id PK
      string slug
      string plan
    }
    data_sources {
      uuid id PK
      uuid org_id FK
      string type
      jsonb connection_config
    }
    monitored_tables {
      uuid id PK
      uuid source_id FK
      string table_name
      jsonb check_config
    }
    table_profiles {
      uuid id PK
      uuid table_id FK
      bigint row_count
      jsonb column_metrics
    }
    check_results {
      uuid id PK
      uuid profile_id FK
      string check_type
      string status
    }
    incidents {
      uuid id PK
      uuid table_id FK
      string severity
      string status
      jsonb llm_narration
    }
    monitors {
      uuid id PK
      uuid table_id FK
      string status
      uuid active_revision_id FK
    }
    monitor_revisions {
      uuid id PK
      uuid monitor_id FK
      int revision
      string definition_hash
    }
    monitor_runs {
      uuid id PK
      uuid revision_id FK
      string status
      jsonb result
    }
""",
    "erd_identity": INIT + """erDiagram
    organizations ||--o{ users : contains
    organizations ||--o{ api_keys : issues
    organizations ||--o{ invites : sends
    organizations ||--o{ teams : groups
    teams ||--o{ team_members : contains
    users ||--o{ team_members : joins
    users ||--o| user_notification_prefs : configures
    teams ||--o{ oncall_schedules : schedules
    users ||--o{ oncall_schedules : covers
    organizations {
      uuid id PK
      string slug
      string plan
      string subscription_status
    }
    users {
      uuid id PK
      uuid org_id FK
      string email
      string role
      bool is_active
    }
    api_keys {
      uuid id PK
      uuid org_id FK
      string name
      string key_hash
    }
    invites {
      uuid id PK
      uuid org_id FK
      string role
      datetime expires_at
    }
    teams {
      uuid id PK
      uuid org_id FK
      string name
      string color
    }
    team_members {
      uuid id PK
      uuid team_id FK
      uuid user_id FK
      string role
    }
    user_notification_prefs {
      uuid id PK
      uuid user_id FK
      bool daily_digest
      int digest_hour
    }
    oncall_schedules {
      uuid id PK
      uuid team_id FK
      uuid user_id FK
      datetime starts_at
      datetime ends_at
    }
    staff_users {
      uuid id PK
      string email
      bool is_active
    }
""",
    "erd_ai_governance": INIT + """erDiagram
    ai_systems ||--o{ ai_system_versions : versions
    ai_system_versions ||--o{ ai_data_use_revisions : declares
    ai_system_versions ||--o{ ai_release_manifests : packages
    ai_systems ||--o{ ai_deployments : deploys
    ai_release_manifests ||--o{ ai_approvals : reviewed_by
    ai_deployments ||--o{ ai_evidence : collects
    ai_evidence o|--o{ ai_control_evaluations : supports
    ai_control_evaluations ||--o| ai_governance_incidents : opens
    ai_systems {
      uuid id PK
      uuid org_id FK
      string lifecycle_status
      string autonomy_level
    }
    ai_system_versions {
      uuid id PK
      uuid system_id FK
      int version_number
      string definition_hash
    }
    ai_data_use_revisions {
      uuid id PK
      uuid version_id FK
      uuid table_id FK
      string schema_fingerprint
    }
    ai_release_manifests {
      uuid id PK
      uuid version_id FK
      string manifest_hash
      datetime evidence_cutoff
    }
    ai_deployments {
      uuid id PK
      uuid system_id FK
      uuid active_manifest_id FK
      int activation_generation
    }
    ai_approvals {
      uuid id PK
      uuid manifest_id FK
      string decision
      string evidence_snapshot_hash
    }
    ai_evidence {
      uuid id PK
      uuid deployment_id FK
      string content_hash
      string evidence_class
    }
    ai_control_evaluations {
      uuid id PK
      uuid evidence_id FK
      string control_id
      string status
      string reason_code
    }
    ai_governance_incidents {
      uuid id PK
      uuid evaluation_id FK
      string dedupe_key
      string severity
      string status
    }
""",
}


def render(name: str, source: str) -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    source_path = SOURCE_DIR / f"{name}.mmd"
    output_path = OUT / f"{name}-doc.png"
    source_path.write_text(source)
    command = [
        "npx", "-y", "@mermaid-js/mermaid-cli",
        "-i", str(source_path), "-o", str(output_path),
        "-b", "white", "-w", "2400", "-H", "1600", "-s", "1.4",
    ]
    subprocess.run(command, cwd=ROOT / "tmp", check=True)
    print(output_path.relative_to(ROOT))


def render_gantt() -> None:
    """Render a report-first Gantt: legible on A4 and editable as SVG."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    (SOURCE_DIR / "gantt.mmd").write_text(DIAGRAMS["gantt"])
    svg_path = SOURCE_DIR / "gantt.svg"
    png_path = OUT / "gantt-doc.png"

    width, height = 2400, 1360
    left, right, top = 590, 90, 250
    plot_w = width - left - right
    row_h = 84
    start = date(2026, 6, 1)
    end = date(2026, 9, 14)
    total_days = (end - start).days
    x = lambda d: left + ((d - start).days / total_days) * plot_w
    tasks = [
        ("Cadrage et état de l'art", date(2026, 6, 1), date(2026, 6, 12), "#34383F"),
        ("Architecture multi-tenant", date(2026, 6, 8), date(2026, 6, 24), "#34383F"),
        ("Sources, découverte, profilage", date(2026, 6, 18), date(2026, 7, 8), "#B1202D"),
        ("Détection hybride et incidents", date(2026, 7, 1), date(2026, 7, 21), "#B1202D"),
        ("Narration IA et alertes", date(2026, 7, 13), date(2026, 7, 31), "#B1202D"),
        ("Moniteurs typés, équipes", date(2026, 7, 24), date(2026, 8, 15), "#B1202D"),
        ("Gouvernance IA observe-only", date(2026, 8, 4), date(2026, 8, 22), "#B1202D"),
        ("Tests et durcissement", date(2026, 8, 10), date(2026, 8, 25), "#7B2730"),
        ("Seed, captures, démonstration", date(2026, 8, 20), date(2026, 8, 29), "#7B2730"),
        ("Rapport et soutenance", date(2026, 8, 17), date(2026, 8, 31), "#7B2730"),
        ("Évolution produit", date(2026, 9, 1), date(2026, 9, 14), "#70757A"),
    ]
    months = [
        ("JUIN", date(2026, 6, 1), date(2026, 7, 1)),
        ("JUILLET", date(2026, 7, 1), date(2026, 8, 1)),
        ("AOÛT", date(2026, 8, 1), date(2026, 9, 1)),
        ("APRÈS PFE", date(2026, 9, 1), end),
    ]
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#FFFFFF"/>
<style>
text {{ font-family: Arial, Helvetica, sans-serif; fill: #202124; }}
.title {{ font-size: 54px; font-weight: 700; }} .sub {{ font-size: 25px; fill: #61656B; }}
.month {{ font-size: 24px; font-weight: 700; letter-spacing: 2px; }} .task {{ font-size: 26px; font-weight: 600; }}
.week {{ font-size: 20px; fill: #70757A; }} .small {{ font-size: 20px; fill: #61656B; }}
</style>
<text x="80" y="78" class="title">Planification du PFE</text>
<text x="80" y="122" class="sub">Du 1er juin au 31 août 2026 — continuité produit matérialisée après la remise</text>
<line x1="80" y1="162" x2="2320" y2="162" stroke="#B1202D" stroke-width="8"/>
''']
    for label, d1, d2 in months:
        mx1, mx2 = x(d1), x(d2)
        fill = "#F8EAEC" if label != "APRÈS PFE" else "#F3F4F6"
        parts.append(f'<rect x="{mx1:.1f}" y="184" width="{mx2-mx1:.1f}" height="58" fill="{fill}"/>')
        parts.append(f'<text x="{(mx1+mx2)/2:.1f}" y="222" class="month" text-anchor="middle">{label}</text>')
    cursor = start
    while cursor <= end:
        gx = x(cursor)
        parts.append(f'<line x1="{gx:.1f}" y1="242" x2="{gx:.1f}" y2="1202" stroke="#DADCE0" stroke-width="2"/>')
        parts.append(f'<text x="{gx+7:.1f}" y="274" class="week">{cursor.day:02d}/{cursor.month:02d}</text>')
        cursor = date.fromordinal(cursor.toordinal() + 7)
    pfe_x = x(date(2026, 8, 31))
    parts.append(f'<line x1="{pfe_x:.1f}" y1="174" x2="{pfe_x:.1f}" y2="1220" stroke="#B1202D" stroke-width="5" stroke-dasharray="14 10"/>')
    parts.append(f'<text x="{pfe_x-14:.1f}" y="1280" font-size="22" font-weight="700" fill="#B1202D" text-anchor="end">31 AOÛT · FIN DE LA PÉRIODE PFE</text>')
    for idx, (label, d1, d2, color) in enumerate(tasks):
        y = top + 62 + idx * row_h
        parts.append(f'<text x="80" y="{y+31}" class="task">{escape(label)}</text>')
        parts.append(f'<line x1="{left}" y1="{y+20}" x2="{width-right}" y2="{y+20}" stroke="#EEF0F2" stroke-width="2"/>')
        bx, bw = x(d1), max(22, x(d2) - x(d1))
        parts.append(f'<rect x="{bx:.1f}" y="{y}" width="{bw:.1f}" height="42" rx="21" fill="{color}"/>')
        parts.append(f'<circle cx="{bx:.1f}" cy="{y+21}" r="8" fill="#FFFFFF" opacity="0.9"/>')
    parts.extend([
        '<rect x="80" y="1238" width="26" height="26" rx="13" fill="#B1202D"/>',
        '<text x="122" y="1260" class="small">Construction du produit</text>',
        '<rect x="420" y="1238" width="26" height="26" rx="13" fill="#7B2730"/>',
        '<text x="462" y="1260" class="small">Validation et livrables</text>',
        '<rect x="810" y="1238" width="26" height="26" rx="13" fill="#70757A"/>',
        '<text x="852" y="1260" class="small">Travaux poursuivis après le PFE</text>',
        '</svg>',
    ])
    svg_path.write_text("".join(parts))
    node = Path("/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
    sharp = Path("/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp")
    script = "const sharp=require(process.argv[1]); sharp(process.argv[2],{density:220}).png().toFile(process.argv[3]).catch(e=>{console.error(e);process.exit(1)})"
    subprocess.run([str(node), "-e", script, str(sharp), str(svg_path), str(png_path)], check=True)
    print(png_path.relative_to(ROOT))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, source in DIAGRAMS.items():
        if name == "gantt":
            continue
        render(name, source)
    render_gantt()
    print(f"Rendered {len(DIAGRAMS) - 1} Mermaid diagrams and one report-first Gantt")


if __name__ == "__main__":
    main()
