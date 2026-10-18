import {afterEach,describe,it,expect,vi} from 'vitest';
import {cleanup,render,screen,fireEvent} from '@testing-library/react';
import EvidenceField from '../src/components/EvidenceField';
import CoveragePanel from '../src/components/CoveragePanel';
import JobGrid,{JobRow} from '../src/components/JobGrid';
afterEach(cleanup);

describe('Evidence review',()=>{
 it('keeps empty extracted lists unknown',()=>{render(<EvidenceField name="required_skills" extracted={[]} value={[]} edited={false} onChange={()=>{}} onFocus={()=>{}}/>);expect(screen.getByText('Unknown')).toBeTruthy();expect(screen.queryByText('high confidence')).toBeNull()});
 it('updates a field and locates its original evidence',()=>{const edit=vi.fn(),focus=vi.fn();render(<EvidenceField name="title" extracted={{value:'Developer',evidence:'Role: Developer',confidence:'high'}} value="Developer" edited={false} onChange={edit} onFocus={focus}/>);fireEvent.change(screen.getByRole('textbox',{name:'Title'}),{target:{value:'Backend Developer'}});expect(edit).toHaveBeenCalledWith('Backend Developer');fireEvent.click(screen.getByRole('button',{name:'“Role: Developer”'}));expect(focus).toHaveBeenCalledWith('Role: Developer')});
});
describe('Honest coverage',()=>{
 it('shows unsupported requirements separately',()=>{render(<CoveragePanel coverage={{must_have_coverage:.5,must_have_total:2,must_have_covered:1,covered_keywords:[{term:'Python',sections:['projects']}],supported_but_not_placed:[],not_in_vault:[{term:'Kubernetes',message:'Not supported by verified facts.'}],ats_phrase_hits:[],warnings:[]}}/>);expect(screen.getByText('50%')).toBeTruthy();expect(screen.getByText('Not in your vault')).toBeTruthy();expect(screen.getByText('Kubernetes')).toBeTruthy();expect(screen.getByRole('progressbar').getAttribute('value')).toBe('1')});
});
describe('Master list inline edit',()=>{
 it('saves status against the correct job ID',()=>{const edit=vi.fn().mockResolvedValue({});const row={job:{id:'job-a',title:'Fixture role',company_name:'Fixture Co'},master:{id:'master-a',status:'to_apply',priority:'medium'}} as JobRow;render(<JobGrid rows={[row]} onEdit={edit}/>);fireEvent.change(screen.getByRole('combobox',{name:'Status for Fixture role'}),{target:{value:'applied'}});expect(edit).toHaveBeenCalledWith('job-a',{status:'applied'})});
});
