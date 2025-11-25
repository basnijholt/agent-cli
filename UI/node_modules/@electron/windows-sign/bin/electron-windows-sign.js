#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const args = require('minimist')(process.argv.slice(2), {
  string: [
    'certificate-file',
    'certificate-password',
    'sign-tool-path',
    'timestamp-server',
    'description',
    'website',
    'sign-with-params'
  ],
  boolean: [
    'help',
    'debug'
  ],
  default: {
    'automatically-select-certificate': true
  }
});
const usage = fs.readFileSync(path.join(__dirname, 'electron-windows-sign-usage.txt')).toString();
const sign = require('../').sign;

args.app = args._.shift();

if (!args.app || args.help) {
  console.log(usage);
  process.exit(0);
}

// Remove excess arguments
delete args._;
delete args.help;

sign(args, function done(err) {
  if (err) {
    console.error('Sign failed:');
    if (err.message) console.error(err.message);
    else if (err.stack) console.error(err.stack);
    else console.log(err);
    process.exit(1);
  }
  console.log('Application signed:', args.app);
  process.exit(0);
});
