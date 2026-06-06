const dbName = "datawatch_nosql";
const database = db.getSiblingDB(dbName);

database.events.drop();

const eventNames = [
  "page_view",
  "checkout_started",
  "payment_failed",
  "subscription_upgraded",
  "invoice_paid",
  "feature_used",
];

const countries = ["US", "FR", "MA", "DE", "GB"];
const browsers = ["Chrome", "Safari", "Firefox", "Edge"];

const documents = [];
for (let i = 1; i <= 250; i += 1) {
  const eventName = eventNames[i % eventNames.length];
  const country = countries[i % countries.length];
  const browser = browsers[i % browsers.length];
  const revenue = eventName === "invoice_paid" ? 29 + (i % 9) * 10 : 0;

  documents.push({
    event_id: `evt_${i}`,
    tenant_id: i % 3 === 0 ? "acme-corp" : "startup-io",
    user_id: i % 17 === 0 ? null : `usr_${1000 + i}`,
    event_name: eventName,
    occurred_at: new Date(Date.now() - i * 60 * 1000),
    metadata: {
      browser,
      country,
      device: i % 4 === 0 ? "mobile" : "desktop",
      campaign: i % 10 === 0 ? null : `campaign_${i % 5}`,
    },
    metrics: {
      revenue,
      duration_ms: 50 + i * 3,
      retry_count: eventName === "payment_failed" ? 1 + (i % 3) : 0,
    },
    flags: {
      bot: false,
      sampled: i % 2 === 0,
    },
  });
}

database.events.insertMany(documents);
database.events.createIndex({ tenant_id: 1, occurred_at: -1 });
database.events.createIndex({ event_name: 1 });

database.audit_logs.drop();
database.audit_logs.insertMany([
  {
    actor: "system",
    action: "seed",
    created_at: new Date(),
    details: { database: dbName, documents: documents.length },
  },
]);
