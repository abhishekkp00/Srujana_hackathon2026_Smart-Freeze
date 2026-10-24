import React, { useEffect, useState } from 'react';
import {
  Cpu,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Play,
  RotateCcw,
  Sparkles,
  Info,
  Scale,
  Database,
  ArrowRight,
} from 'lucide-react';
import {
  getMLStatus,
  getMLEvaluation,
  getMLDemoSamples,
  predictFraud,
} from '../api/endpoints';
import {
  MLStatusData,
  MLEvaluationReport,
  MLDemoSample,
  MLPredictResponse,
} from '../types';
import { StatCard } from '../components/common/StatCard';
import { Badge } from '../components/common/Badge';

export const MLAnalysis: React.FC = () => {
  const [status, setStatus] = useState<MLStatusData | null>(null);
  const [evaluation, setEvaluation] = useState<MLEvaluationReport | null>(null);
  const [demoSamples, setDemoSamples] = useState<MLDemoSample[]>([]);
  const [selectedSampleId, setSelectedSampleId] = useState<string>('');
  
  // Feature input state for interactive prediction
  const [currentFeatures, setCurrentFeatures] = useState<Record<string, number>>({});
  const [prediction, setPrediction] = useState<MLPredictResponse | null>(null);
  const [isPredicting, setIsPredicting] = useState<boolean>(false);
  const [predictError, setPredictError] = useState<string | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const statData = await getMLStatus();
        setStatus(statData);

        // An unavailable model is a valid runtime state; show its status and training instructions.
        if (statData.status !== 'LOADED') {
          setEvaluation(null);
          setDemoSamples([]);
          return;
        }

        const [evalData, samples] = await Promise.all([getMLEvaluation(), getMLDemoSamples()]);
        setEvaluation(evalData);
        setDemoSamples(samples);

        if (samples.length > 0) {
          setSelectedSampleId(samples[0].sample_id);
          setCurrentFeatures(samples[0].features);
        }
      } catch (err: any) {
        console.error('Failed to load ML analysis data:', err);
        setError(err?.response?.data?.detail || err?.message || 'Failed to load model metadata.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleSelectSample = (sampleId: string) => {
    setSelectedSampleId(sampleId);
    const found = demoSamples.find((s) => s.sample_id === sampleId);
    if (found) {
      setCurrentFeatures({ ...found.features });
      setPrediction(null);
      setPredictError(null);
    }
  };

  const handleFeatureChange = (featName: string, valStr: string) => {
    const num = valStr.trim() === '' ? Number.NaN : Number(valStr);
    setCurrentFeatures((prev) => ({
      ...prev,
      [featName]: num,
    }));
  };

  const handleRunPrediction = async () => {
    setPredictError(null);
    const requiredFeatures = status?.features ?? [];
    const invalidFeatures = requiredFeatures.filter((feature) => !Number.isFinite(currentFeatures[feature]));
    if (invalidFeatures.length > 0) {
      setPredictError('Enter a finite numeric value for: ' + invalidFeatures.join(', '));
      return;
    }
    setIsPredicting(true);
    try {
      const res = await predictFraud(currentFeatures);
      setPrediction(res);
    } catch (err: any) {
      console.error('Prediction failed:', err);
      setPredictError(err?.response?.data?.detail || err?.message || 'Prediction request failed');
    } finally {
      setIsPredicting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full py-20 text-slate-500 space-x-2">
        <Cpu className="w-6 h-6 animate-spin text-teal-600" />
        <span className="text-sm font-medium">Loading ML Model Analysis & Evaluation Data...</span>
      </div>
    );
  }

  if (error || !status) {
    return (
      <div className="space-y-4">
        <div className="fh-error">
          <strong>Model status could not be retrieved</strong>
          <p className="mt-2">{error || 'The API did not return a model status.'}</p>
        </div>
      </div>
    );
  }

  if (status.status !== 'LOADED') {
    return (
      <div className="space-y-5">
        <div className="surface p-6">
          <div className="eyebrow">Machine learning / Model readiness</div>
          <h2 className="page-heading mt-2">No verified model is available</h2>
          <p className="page-subheading mt-2">{status.message || 'The model artifact is not loaded or did not pass integrity verification.'}</p>
          <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            Predictions are disabled until training succeeds and the model artifact passes its SHA-256 integrity check.
          </div>
          <div className="mt-4">
            <div className="eyebrow">Training command</div>
            <code className="mt-2 block rounded-md bg-[#202b2a] p-3 text-sm text-white">python scripts/train_ml_model.py</code>
            <p className="mt-2 text-xs text-slate-500">Dataset expected at data/raw/creditcard.csv. The command must run successfully before metrics or predictions can be shown.</p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !evaluation) {
    return (
      <div className="space-y-4">
        <div className="fh-error">
          <strong>Model loaded, but evaluation data is unavailable</strong>
          <p className="mt-2">{error || 'The API did not return the evaluation metadata.'}</p>
          <p className="mt-2 text-xs">Re-run the training pipeline and verify that its artifact, metadata and demo samples are from the same training run.</p>
        </div>
      </div>
    );
  }

  const primary = evaluation.primary_model_metrics;
  const baseline = evaluation.baseline_model_metrics;
  const cm = primary.confusion_matrix;
  const activeSample = demoSamples.find((s) => s.sample_id === selectedSampleId);

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Banner: Model Status & Provenance */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-teal-50 border border-teal-100 text-teal-700">
              <Cpu className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-xl font-bold text-slate-900">
                  Transaction Fraud Classifier
                </h2>
                <Badge variant="success" size="sm">
                  {status.status}
                </Badge>
                <Badge variant="info" size="sm">
                  {status.model_version}
                </Badge>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Dataset: {evaluation.dataset_source}. Historical credit-card benchmark; not an Indian bank AML model.
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 border border-slate-200">
            Algorithm: {evaluation.selected_model}
          </span>
          <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-teal-50 text-teal-800 border border-teal-200">
            Decision Threshold: {evaluation.selected_threshold.toFixed(2)}
          </span>
        </div>
      </div>

      {/* KPI Stat Cards: Held-Out Test Evaluation */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
            Held-out test metrics ({evaluation.test_size.toLocaleString()} transactions)
          </h3>
          <span className="text-xs text-slate-500 font-medium">
            Strictly untouched during training and threshold tuning
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard
            label="PR-AUC"
            value={primary.pr_auc.toFixed(4)}
            subtext="Average Precision"
            icon={Sparkles}
          />
          <StatCard
            label="F1-Score"
            value={(primary.f1_score * 100).toFixed(1) + '%'}
            subtext={`Threshold ${primary.threshold_used.toFixed(2)}`}
            icon={Cpu}
          />
          <StatCard
            label="Precision"
            value={(primary.precision * 100).toFixed(1) + '%'}
            subtext="Positive class: fraud"
            icon={ShieldCheck}
          />
          <StatCard
            label="Recall"
            value={(primary.recall * 100).toFixed(1) + '%'}
            subtext="Share of labelled fraud cases detected"
            icon={CheckCircle2}
          />
          <StatCard
            label="ROC-AUC"
            value={primary.roc_auc.toFixed(4)}
            subtext="Discrimination"
            icon={Scale}
          />
          <StatCard
            label="Accuracy"
            value={(primary.accuracy * 100).toFixed(2) + '%'}
            subtext="Supplementary"
            icon={Database}
          />
        </div>
      </div>

      {/* Grid: Confusion Matrix & Model Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Confusion Matrix (5 cols) */}
        <div className="lg:col-span-5 bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Held-Out Confusion Matrix</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Performance breakdown on {evaluation.test_size.toLocaleString()} held-out samples at threshold {primary.threshold_used.toFixed(2)}.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200">
              <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider block">
                True Positives (TP)
              </span>
              <span className="text-2xl font-extrabold text-emerald-900 mt-1 block font-mono">
                {cm.true_positives}
              </span>
              <span className="text-[11px] text-emerald-700 mt-1 block">
                Fraud accurately flagged
              </span>
            </div>

            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200">
              <span className="text-xs font-semibold text-amber-800 uppercase tracking-wider block">
                False Positives (FP)
              </span>
              <span className="text-2xl font-extrabold text-amber-900 mt-1 block font-mono">
                {cm.false_positives}
              </span>
              <span className="text-[11px] text-amber-700 mt-1 block">
                Legitimate transactions incorrectly flagged
              </span>
            </div>

            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200">
              <span className="text-xs font-semibold text-rose-800 uppercase tracking-wider block">
                False Negatives (FN)
              </span>
              <span className="text-2xl font-extrabold text-rose-900 mt-1 block font-mono">
                {cm.false_negatives}
              </span>
              <span className="text-[11px] text-rose-700 mt-1 block">
                Fraud cases missed
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                True Negatives (TN)
              </span>
              <span className="text-2xl font-extrabold text-slate-900 mt-1 block font-mono">
                {cm.true_negatives.toLocaleString()}
              </span>
              <span className="text-[11px] text-slate-600 mt-1 block">
                Legitimate accurately cleared
              </span>
            </div>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 text-xs text-slate-600 space-y-1">
            <div className="flex justify-between">
              <span className="font-medium text-slate-500">Total Test Transactions:</span>
              <span className="font-mono font-semibold text-slate-800">{evaluation.test_size.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="font-medium text-slate-500">Test Fraud Cases (Class 1):</span>
              <span className="font-mono font-semibold text-rose-700">{cm.true_positives + cm.false_negatives} ({evaluation.test_size ? (((cm.true_positives + cm.false_negatives) / evaluation.test_size) * 100).toFixed(3) : "n/a"}% of test set)</span>
            </div>
            <div className="flex justify-between">
              <span className="font-medium text-slate-500">Threshold Rationale:</span>
              <span className="text-[11px] text-slate-700 text-right max-w-xs">{primary.threshold_selection_reason}</span>
            </div>
          </div>
        </div>

        {/* Model Comparison Table (7 cols) */}
        <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Model Evaluation Comparison</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Primary Random Forest vs Baseline Logistic Regression on identical test partitions.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-b border-slate-200 uppercase text-[11px] font-semibold text-slate-600">
                <tr>
                  <th className="py-2.5 px-3">Metric</th>
                  <th className="py-2.5 px-3 text-teal-800 font-bold">Random Forest (Primary)</th>
                  <th className="py-2.5 px-3 text-slate-600">Logistic Regression (Baseline)</th>
                  <th className="py-2.5 px-3 text-right">Advantage</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                <tr>
                  <td className="py-2.5 px-3 font-semibold text-slate-700">F1-Score</td>
                  <td className="py-2.5 px-3 font-mono font-bold text-teal-700">{(primary.f1_score * 100).toFixed(2)}%</td>
                  <td className="py-2.5 px-3 font-mono text-slate-600">{(baseline.f1_score * 100).toFixed(2)}%</td>
                  <td className="py-2.5 px-3 font-semibold text-right text-emerald-600">
                    +{((primary.f1_score - baseline.f1_score) * 100).toFixed(1)}%
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 font-semibold text-slate-700">Precision</td>
                  <td className="py-2.5 px-3 font-mono font-bold text-teal-700">{(primary.precision * 100).toFixed(2)}%</td>
                  <td className="py-2.5 px-3 font-mono text-slate-600">{(baseline.precision * 100).toFixed(2)}%</td>
                  <td className="py-2.5 px-3 font-semibold text-right text-emerald-600">
                    +{((primary.precision - baseline.precision) * 100).toFixed(1)}%
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 font-semibold text-slate-700">Recall</td>
                  <td className="py-2.5 px-3 font-mono font-bold text-teal-700">{(primary.recall * 100).toFixed(2)}%</td>
                  <td className="py-2.5 px-3 font-mono text-slate-600">{(baseline.recall * 100).toFixed(2)}%</td>
                  <td className="py-2.5 px-3 text-right text-slate-400">
                    {((primary.recall - baseline.recall) * 100 >= 0 ? '+' : '') + ((primary.recall - baseline.recall) * 100).toFixed(1) + ' percentage points'}
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 font-semibold text-slate-700">PR-AUC (Avg Precision)</td>
                  <td className="py-2.5 px-3 font-mono font-bold text-teal-700">{primary.pr_auc.toFixed(4)}</td>
                  <td className="py-2.5 px-3 font-mono text-slate-600">{baseline.pr_auc.toFixed(4)}</td>
                  <td className="py-2.5 px-3 font-semibold text-right text-emerald-600">
                    +{(primary.pr_auc - baseline.pr_auc).toFixed(4)}
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 font-semibold text-slate-700">ROC-AUC</td>
                  <td className="py-2.5 px-3 font-mono font-bold text-teal-700">{primary.roc_auc.toFixed(4)}</td>
                  <td className="py-2.5 px-3 font-mono text-slate-600">{baseline.roc_auc.toFixed(4)}</td>
                  <td className="py-2.5 px-3 font-semibold text-right text-emerald-600">
                    +{(primary.roc_auc - baseline.roc_auc).toFixed(4)}
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 font-semibold text-slate-700">Operating Threshold</td>
                  <td className="py-2.5 px-3 font-mono text-slate-800">{primary.threshold_used.toFixed(2)}</td>
                  <td className="py-2.5 px-3 font-mono text-slate-800">{baseline.threshold_used.toFixed(2)}</td>
                  <td className="py-2.5 px-3 text-right text-slate-400">—</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 text-xs text-slate-600 space-y-1.5">
            <h4 className="font-bold text-slate-800 flex items-center">
              <Info className="w-3.5 h-3.5 mr-1 text-teal-600" />
              Evaluation Insights
            </h4>
            <p>
              The held-out fraud prevalence is {evaluation.test_size ? (((cm.true_positives + cm.false_negatives) / evaluation.test_size) * 100).toFixed(3) : 'not available'}%. Accuracy alone can hide poor minority-class performance. Accuracy was {(baseline.accuracy * 100).toFixed(2)}% for the baseline and {(primary.accuracy * 100).toFixed(2)}% for the selected model; compare precision, recall and PR-AUC alongside it.
            </p>
          </div>
        </div>
      </div>

      {/* Interactive Prediction Panel */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-200 bg-slate-50 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900 flex items-center">
              <Sparkles className="w-5 h-5 mr-2 text-teal-600" />
              Interactive Transaction Prediction Inspector
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Select a held-out dataset sample or adjust its feature vector, then request a fresh backend inference via <code className="font-mono bg-white px-1.5 py-0.5 rounded border border-slate-200">POST /api/ml/predict</code>.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <span className="text-xs font-semibold text-slate-600">Held-out samples:</span>
            <select
              value={selectedSampleId}
              onChange={(e) => handleSelectSample(e.target.value)}
              disabled={demoSamples.length === 0}
              className="bg-white border border-slate-200 text-xs font-semibold rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:opacity-50"
            >
              {demoSamples.map((s) => (
                <option key={s.sample_id} value={s.sample_id}>
                  [{s.ground_truth_label}] {s.description.slice(0, 50)}...
                </option>
              ))}
            </select>
            <button
              onClick={handleRunPrediction}
              disabled={isPredicting || demoSamples.length === 0}
              className="flex items-center space-x-1.5 px-4 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-xs font-bold shadow-sm transition-colors disabled:opacity-60"
            >
              <Play className="w-3.5 h-3.5" />
              <span>{isPredicting ? 'Evaluating...' : 'Run ML Prediction'}</span>
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          {/* Active Sample Context & Prediction Result Banner */}
          {activeSample && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs gap-3">
              <div>
                <span className="font-semibold text-slate-500 block">Selected Test Record:</span>
                <span className="font-bold text-slate-900 text-sm">{activeSample.description}</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-slate-500 font-medium">Dataset label (held-out record):</span>
                <Badge variant={activeSample.ground_truth_class === 1 ? 'danger' : 'neutral'} size="sm">
                  {activeSample.ground_truth_label}
                </Badge>
              </div>
            </div>
          )}

          {/* Prediction Outcome Card (if computed) */}
          {prediction && (
            <div className={`p-5 rounded-xl border ${prediction.predicted_class === 1 ? 'bg-rose-50/70 border-rose-200' : 'bg-emerald-50/70 border-emerald-200'} transition-all`}>
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-center space-x-3">
                  {prediction.predicted_class === 1 ? (
                    <div className="p-2.5 rounded-full bg-rose-100 text-rose-700">
                      <XCircle className="w-6 h-6" />
                    </div>
                  ) : (
                    <div className="p-2.5 rounded-full bg-emerald-100 text-emerald-700">
                      <CheckCircle2 className="w-6 h-6" />
                    </div>
                  )}
                  <div>
                    <div className="flex items-center space-x-2">
                      <h4 className="text-base font-bold text-slate-900">
                        Model classification: {prediction.predicted_label === 'FRAUD' ? 'FRAUD PATTERN FLAG' : 'NON-FRAUD PATTERN'}
                      </h4>
                      <Badge variant={prediction.predicted_class === 1 ? 'danger' : 'success'} size="sm">
                        Class {prediction.predicted_class}
                      </Badge>
                    </div>
                    <p className="text-xs text-slate-600 mt-1 max-w-2xl">
                      {prediction.explanation}
                    </p>
                  </div>
                </div>

                <div className="text-right flex-shrink-0">
                  <div className="text-xs text-slate-500 font-medium">Model Fraud Score</div>
                  <div className="text-2xl font-black font-mono text-slate-900">
                    {prediction.model_score.toFixed(4)}
                  </div>
                  <div className="text-[11px] text-slate-500 font-mono">
                    Decision Threshold: {prediction.threshold_used.toFixed(2)}
                  </div>
                </div>
              </div>

              {/* Score Bar visualization */}
              <div className="mt-4 pt-3 border-t border-slate-200/60">
                <div className="flex justify-between text-[11px] text-slate-500 mb-1">
                  <span>0.00 (lower model score)</span>
                  <span className="font-semibold text-slate-700">Operating Threshold ({prediction.threshold_used.toFixed(2)})</span>
                  <span>1.00 (higher model score)</span>
                </div>
                <div className="relative w-full h-3 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${prediction.predicted_class === 1 ? 'bg-rose-500' : 'bg-teal-500'}`}
                    style={{ width: `${Math.min(Math.max(prediction.model_score * 100, 2), 100)}%` }}
                  />
                  {/* Threshold vertical marker */}
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-slate-900 z-10"
                    style={{ left: `${prediction.threshold_used * 100}%` }}
                    title={`Threshold: ${prediction.threshold_used}`}
                  />
                </div>
              </div>
            </div>
          )}

          {predictError && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{predictError}</span>
            </div>
          )}

          {demoSamples.length === 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs leading-5 text-amber-900">
              The model artifact is loaded, but its generated demo-sample file is missing or empty. Interactive sample prediction is disabled rather than using fabricated vectors. Re-run <code>python scripts/train_ml_model.py</code> with <code>data/raw/creditcard.csv</code> available to regenerate both artifacts.
            </div>
          )}

          {/* Feature Grid Inspector */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                Feature Vector Inspector (30 Input Dimensions)
              </h4>
              <button
                onClick={() => {
                  if (activeSample) setCurrentFeatures({ ...activeSample.features });
                }}
                className="text-xs text-slate-500 hover:text-teal-600 flex items-center space-x-1"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset to Sample Values</span>
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-3 max-h-80 overflow-y-auto p-3 bg-slate-50/50 rounded-xl border border-slate-200">
              {Object.keys(currentFeatures).map((feat) => (
                <div key={feat} className="bg-white p-2 rounded-lg border border-slate-200 text-xs">
                  <label className="text-[11px] font-mono font-semibold text-slate-500 block truncate">
                    {feat}
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={currentFeatures[feat]}
                    onChange={(e) => handleFeatureChange(feat, e.target.value)}
                    className="w-full mt-1 font-mono text-xs font-bold text-slate-800 bg-slate-50 px-2 py-1 rounded border border-slate-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Governance & Architectural Boundary Notice */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 text-slate-600 space-y-2 text-xs">
        <h4 className="font-bold text-slate-800 flex items-center">
          <ShieldCheck className="w-4 h-4 mr-1.5 text-teal-600" />
          Mandatory Human-in-the-Loop Governance Notice & ML Scope
        </h4>
        <p>
          {evaluation.governance_notice}
        </p>
        <p className="text-slate-500">
          <strong>Architectural Boundary:</strong> This credit-card transaction risk model operates strictly as an exploratory indicator. It does not interface with, alter, or influence the internal integer-paise ledger reconstruction, Proportional fund tracing, First-In First-Out (FIFO) tracing, Lowest Intermediate Balance Rule (LIBR) tracking, or Consensus Lien recovery bounds.
        </p>
      </div>
    </div>
  );
};
