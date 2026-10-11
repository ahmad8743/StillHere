const fs = require('node:fs');
const Ajv = require('ajv/dist/2020');
const standalone = require('ajv/dist/standalone').default;
const { _Code } = require('ajv/dist/compile/codegen/code');
const schema = require('../contracts/finance-update.schema.json');
const ledgerSchema = require('../contracts/finance-ledger.schema.json');
const forecastSchema = require('../contracts/finance-forecast.schema.json');
const validDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
const ajv = new Ajv({ strict: false, allErrors: true, code: { source: true, formats: new _Code(`({date: ${validDate.toString()}})`) } });
ajv.addFormat('date', validDate);
for (const definition of [schema, ledgerSchema, forecastSchema]) ajv.addSchema(definition);
// Inline Unicode length so the generated browser validator needs no package loader.
const compiled = standalone(ajv, {
  validateUpdate: schema.$id,
  validateLedger: ledgerSchema.$id,
  validateUpdateResult: `${ledgerSchema.$id}#/$defs/UpdateResult`,
  validateForecastInput: `${forecastSchema.$id}#/$defs/Input`,
  validateForecastOutput: `${forecastSchema.$id}#/$defs/Output`,
  validateProjection: `${forecastSchema.$id}#/$defs/Projection`
}).replaceAll('require("ajv/dist/runtime/ucs2length").default', '((value) => Array.from(value).length)');
if (/require\(/.test(compiled)) throw new Error('Generated validator unexpectedly needs runtime packages.');
const output = `/* Generated from contracts/finance-*.schema.json. Run npm run build:finance-contract. */\n(() => {\n  const compiled = { exports: {} };\n  ((module, exports) => {\n${compiled}\n  })(compiled, compiled.exports);\n  const api = Object.freeze(compiled.exports);\n  if (typeof module !== 'undefined' && module.exports) module.exports = api;\n  if (typeof window !== 'undefined') window.StillHereFinanceValidation = api;\n})();\n// Built by Raneem Mousa\n`;
const target = 'frontend/finance-validation.js';
if (process.argv.includes('--check')) {
  if (!fs.existsSync(target) || fs.readFileSync(target, 'utf8') !== output) throw new Error('Finance validator is stale. Run npm run build:finance-contract.');
} else fs.writeFileSync(target, output);
// Built by Raneem Mousa
