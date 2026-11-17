import test from 'node:test';import assert from 'node:assert/strict';import {memoryProfile} from '../src/colab-core.js';
const info={specs:[{accelerator:'L4'},{accelerator:'T4'}],highMemorySpecs:[{accelerator:'A100'},{accelerator:'T4'}]};
test('L4 auto chooses the eligible standard RAM profile without switching accelerator',()=>{assert.equal(memoryProfile('L4',info),'standard');assert.equal(memoryProfile('L4',info,'high'),null);assert.equal(memoryProfile('A100',info),'high');assert.equal(memoryProfile('T4',info),'standard');assert.equal(memoryProfile('H100',info),null);});
