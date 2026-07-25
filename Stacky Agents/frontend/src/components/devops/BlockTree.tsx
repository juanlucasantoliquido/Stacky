/**
 * BlockTree (Plan 87 F5)
 * Render recursivo de stages/jobs/steps como bloques anidados
 */
import React from 'react';
import type { PipelineSpecDraft, StageDraft, JobDraft, StepDraft } from '../../devops/specBuilder';
import { addStage, addJob, addStep, removeStage, removeJob, removeStep } from '../../devops/specBuilder';
import styles from './devops.module.css';

export interface BlockTreeProps {
  spec: PipelineSpecDraft;
  setSpec: (spec: PipelineSpecDraft) => void;
  selected: { si?: number; ji?: number; sti?: number } | null;
  setSelected: (selected: { si?: number; ji?: number; sti?: number } | null) => void;
}

const StageBlock: React.FC<{
  stage: StageDraft;
  si: number;
  spec: PipelineSpecDraft;
  setSpec: (spec: PipelineSpecDraft) => void;
  selected: { si?: number; ji?: number; sti?: number } | null;
  setSelected: (selected: { si?: number; ji?: number; sti?: number } | null) => void;
}> = ({ stage, si, spec, setSpec, selected, setSelected }) => {
  const isSelected = selected?.si === si && selected.ji === undefined && selected.sti === undefined;

  return (
    <div
      className={isSelected ? `${styles.blockStage} ${styles.blockStageSelected}` : styles.blockStage}
      onClick={() => setSelected({ si })}
    >
      <div className={styles.blockTree__head}>
        <strong>📋 Stage: {stage.name || '(sin nombre)'}</strong>
        <div>
          <button onClick={() => setSpec(removeStage(spec, si))} className={styles.blockTree__btn}>
            ✕
          </button>
          <button onClick={() => setSpec(addJob(spec, si))} className={styles.blockTree__btnNext}>
            + job
          </button>
        </div>
      </div>
      {stage.jobs.map((job, ji) => (
        <JobBlock
          key={`${si}-${ji}`}
          job={job}
          si={si}
          ji={ji}
          spec={spec}
          setSpec={setSpec}
          selected={selected}
          setSelected={setSelected}
        />
      ))}
    </div>
  );
};

const JobBlock: React.FC<{
  job: JobDraft;
  si: number;
  ji: number;
  spec: PipelineSpecDraft;
  setSpec: (spec: PipelineSpecDraft) => void;
  selected: { si?: number; ji?: number; sti?: number } | null;
  setSelected: (selected: { si?: number; ji?: number; sti?: number } | null) => void;
}> = ({ job, si, ji, spec, setSpec, selected, setSelected }) => {
  const isSelected = selected?.si === si && selected?.ji === ji && selected.sti === undefined;

  return (
    <div
      className={isSelected ? `${styles.blockJob} ${styles.blockJobSelected}` : styles.blockJob}
      onClick={(e) => { e.stopPropagation(); setSelected({ si, ji }); }}
    >
      <div className={styles.blockTree__headSm}>
        <strong>⚙️ Job: {job.name || '(sin nombre)'}</strong>
        <div>
          <button onClick={() => setSpec(removeJob(spec, si, ji))} className={styles.blockTree__btnSm}>
            ✕
          </button>
          <button onClick={() => setSpec(addStep(spec, si, ji))} className={styles.blockTree__btnSmNext}>
            + step
          </button>
        </div>
      </div>
      {job.steps.map((step, sti) => (
        <StepBlock
          key={`${si}-${ji}-${sti}`}
          step={step}
          si={si}
          ji={ji}
          sti={sti}
          spec={spec}
          setSpec={setSpec}
          selected={selected}
          setSelected={setSelected}
        />
      ))}
    </div>
  );
};

const StepBlock: React.FC<{
  step: StepDraft;
  si: number;
  ji: number;
  sti: number;
  spec: PipelineSpecDraft;
  setSpec: (spec: PipelineSpecDraft) => void;
  selected: { si?: number; ji?: number; sti?: number } | null;
  setSelected: (selected: { si?: number; ji?: number; sti?: number } | null) => void;
}> = ({ step, si, ji, sti, spec, setSpec, selected, setSelected }) => {
  const isSelected = selected?.si === si && selected?.ji === ji && selected.sti === sti;

  return (
    <div
      className={isSelected ? `${styles.blockStep} ${styles.blockStepSelected}` : styles.blockStep}
      onClick={(e) => { e.stopPropagation(); setSelected({ si, ji, sti }); }}
    >
      <div className={styles.blockTree__headBare}>
        <span>📝 Step: {step.name || '(sin nombre)'}</span>
        <button
          onClick={() => setSpec(removeStep(spec, si, ji, sti))}
          className={styles.blockTree__btnXs}
        >
          ✕
        </button>
      </div>
    </div>
  );
};

export const BlockTree: React.FC<BlockTreeProps> = ({ spec, setSpec, selected, setSelected }) => {
  return (
    <div>
      {spec.stages.map((stage, si) => (
        <StageBlock
          key={`${si}`}
          stage={stage}
          si={si}
          spec={spec}
          setSpec={setSpec}
          selected={selected}
          setSelected={setSelected}
        />
      ))}
    </div>
  );
};
