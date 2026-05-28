use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct ProgressTracker {
    pub total_steps: usize,
    pub current_step: Arc<AtomicUsize>,
    pub steps: Vec<ProgressStep>,
    pub verbose: bool,
}

#[derive(Debug, Clone)]
pub struct ProgressStep {
    pub name: &'static str,
    pub status: StepStatus,
    pub message: Option<String>,
}

#[derive(Debug, Clone)]
pub enum StepStatus {
    Pending,
    Running,
    Completed,
    Failed(String),
    Skipped,
}

impl ProgressTracker {
    pub fn new(steps: Vec<&'static str>) -> Self {
        Self {
            total_steps: steps.len(),
            current_step: Arc::new(AtomicUsize::new(0)),
            steps: steps
                .into_iter()
                .map(|name| ProgressStep {
                    name,
                    status: StepStatus::Pending,
                    message: None,
                })
                .collect(),
            verbose: false,
        }
    }

    pub fn advance(&mut self) -> usize {
        let idx = self.current_step.fetch_add(1, Ordering::SeqCst);
        if idx < self.steps.len() {
            self.steps[idx].status = StepStatus::Running;
        }
        idx
    }

    pub fn complete_step(&mut self, idx: usize) {
        if idx < self.steps.len() {
            self.steps[idx].status = StepStatus::Completed;
        }
    }

    pub fn fail_step(&mut self, idx: usize, msg: String) {
        if idx < self.steps.len() {
            self.steps[idx].status = StepStatus::Failed(msg);
        }
    }
}

impl std::fmt::Display for ProgressTracker {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        for step in &self.steps {
            let icon = match &step.status {
                StepStatus::Pending => "⏳",
                StepStatus::Running => "🔄",
                StepStatus::Completed => "✅",
                StepStatus::Failed(_) => "❌",
                StepStatus::Skipped => "⏭️",
            };
            let msg = step.message.as_deref().unwrap_or("");
            writeln!(f, "  {} {} {}", icon, step.name, msg)?;
        }
        Ok(())
    }
}
