# Reputation as a belief

Written 2026-11-19. Code: `rain/belief.py`, `rain/ladder.py`. Experiments: `experiments/bayes_decay`,
`experiments/anchored_fee`. Each section says what is derived, what is an approximation and what is only
checked on synthetic data.

The protocol's original reputation score answered no stated question: it went up 25 for a kept promise and
down 100 for a broken one. This note starts from the question a lender actually has,

> how likely is this person to keep their next promise?

and derives what the score should be, why it should decay, and how large the next loan can be.

## 1. If people never changed

Let $\theta$ be the probability that a user keeps a promise, and let $\theta \sim \mathrm{Beta}(a_0, b_0)$ across
the population (the prior: what we believe about a stranger). After $K$ kept and $B$ broken promises,

$$\theta \mid \text{data} \sim \mathrm{Beta}(a_0 + K,\; b_0 + B), \qquad \hat p = \frac{a_0 + K}{a_0 + b_0 + K + B}.$$

Reputation is two numbers, $K$ and $B$. Nothing decays: every promise ever made counts equally for ever.
That is correct only if $\theta$ is fixed for life.

## 2. People change: the evidence has to survive

Suppose that between any two promises, with probability $h$, the user's circumstances change and their
$\theta$ is drawn afresh from the population. A promise kept $\tau$ steps ago is evidence about the present
user only if no change happened since, which has probability $\gamma^\tau$ with $\gamma = 1 - h$.

This is the argument of [discounting via uncertainty](https://act65.github.io/discounting-via-uncertainty/)
applied to the past instead of the future. There, the worlds are split into those where the reward
opportunity survives an action and those where it does not, and $\gamma$ is the posterior weight on the
first set. Here the worlds are split into those where the person is still who the evidence describes and
those where they are not. In the first the posterior applies; in the second we know only the prior. So

$$p(\theta_{t+1} \mid \text{data}_t) = \gamma\, p(\theta_t \mid \text{data}_t) + (1 - \gamma)\, \pi(\theta),$$

and taking the mean,

$$\hat p_{t+1} = \gamma\, \hat p_t + (1 - \gamma)\, p_0 .$$

**With no new evidence, the estimate regresses geometrically to the prior mean.** This step is exact. It is
"recent data informs the estimate, but it decays to a prior with time", derived instead of assumed, and the
decay rate is a belief about how fast people change, not a design choice.

What is not exact is carrying this forward. The mixture above is no longer a Beta distribution, and after
each new promise it gains a component. The exact filter tracks a distribution over how long ago the last
change was (`belief.exact_predictive`; checked against brute-force enumeration of every change pattern in
`tests/unit/test_belief.py`). Its state grows with the length of the history.

## 3. What a contract can store: two decaying counters

Replace the mixture by a single Beta whose counts are pulled towards the prior:

$$K \leftarrow \gamma K, \qquad B \leftarrow \gamma B \qquad \text{before each new promise.}$$

This is not the mixture of section 2. It is the geometric mean
$p(\theta \mid \text{data})^{\gamma}\, \pi(\theta)^{1-\gamma}$, renormalised (an identity for Beta
distributions; checked numerically in the tests). Equivalently it is the distribution $q$ that minimises
$\gamma\, \mathrm{KL}(q \,\|\, \text{posterior}) + (1 - \gamma)\, \mathrm{KL}(q \,\|\, \text{prior})$: the best
compromise between what the data said and knowing nothing. (I believe this characterisation of exponential
forgetting is due to Kulhavý and Zarrop, 1993; check before citing.) Section 2 pools arithmetically and
section 3 geometrically; they agree that the estimate regresses to the prior and differ in how.

How much does the cheap rule lose? On data drawn from the model (`experiments/bayes_decay`, 5 seeds):

| $h$ | gap closed at $\gamma = 1 - h$ | best $\gamma$ on the grid | gap closed at the best $\gamma$ |
|---|---|---|---|
| 0.005 | 35% | 0.97 | 82% |
| 0.02 | 70% | 0.94 | 93% |
| 0.05 | 87% | 0.90 (edge of grid) | 97% |

"Gap closed" is the share of the difference in log loss between never forgetting and the exact filter.
Two things follow.

- Two decaying counters are an adequate representation, **provided the decay rate is tuned**.
- **The right decay rate is not $h$.** The counters should forget 2 to 6 times faster than people change:
  the best $1 - \gamma$ is close to $0.42\sqrt{h}$ at all three hazards. The reason is a trade-off. Forgetting
  faster makes the estimate noisier, in proportion to $1 - \gamma$. Forgetting slower leaves evidence about a
  person who no longer exists, in proportion to $h / (1 - \gamma)$. The sum is least when $1 - \gamma \propto
  \sqrt{h}$. I had predicted $\gamma = 1 - h$ would be best and was wrong; the square-root rule is an
  explanation fitted afterwards to three points, and the constant depends on the prior.

### Is the decay slow?

It is as slow as people are stable. If a borrower's reliability changes about once in 200 promises, the best
decay is about 3% per promise: a memory of roughly 33 promises. Two caveats. The model's clock ticks per
promise; if change happens in calendar time the decay should too, and how much evidence arrives per year
then matters. And $h$ is an empirical quantity. Once there is a real promise log, $\gamma$ should be chosen
to maximise the predictive likelihood on it, which is the "learn your own $\gamma$" of the blog post.

### What this says about the score

Since this note was written the contracts have adopted decay, a reward proportional to the fee paid, and
fees paid out to holders (`experiments/anchored_fee`). On 2026-11-19 they also adopted the first and last
points below: each account has a second fading counter for broken promises, weighted like kept ones by the
fee paid, `RainReputation.reliability` returns the posterior mean for a prior the reader supplies, and the
flat 100-point penalty is gone. The point about the maximum is still open.


- The score should be two counters and a prior, read as $\hat p = (a_0 + K)/(a_0 + b_0 + K + B)$. A single
  number cannot distinguish a stranger from someone with a long mixed record.
- The asymmetry (+25, -100) has no place in the belief. A broken promise is one observation, as a kept one
  is. A lender who loses more from a default than they gain from a repayment should express that in the
  risk they accept (section 5), not in the estimate.
- Decay also sets what reputation is worth. With a fixed price per point and fees paid out to holders, a
  point is worth $\delta / (r + \delta)$ of its cost (`experiments/anchored_fee`): decay acts as an extra
  discount rate, which is the blog post's point again.

## 4. Counting promises is not enough: size

The Beta model treats a promise to repay 10 and a promise to repay 10,000 as the same kind of evidence. They
are not, and experiment `exit_scam` shows what goes wrong: a long record of small kept promises is the
cheapest way to prepare a large default.

A model in which size matters: each borrower has a private cost of defaulting, $c$ (what their standing is
worth to them). They repay when the amount due is at most $c$, except that with probability $q$ a shock
makes them default anyway. Then repaying an amount $M$ reveals $c \ge M$, and the sufficient statistic of a
clean record is not how many promises were kept but **the largest amount repaid**.

Let $c$ follow a Pareto distribution across borrowers, $P(c > x) = (x_{\min}/x)^{a}$, which has no natural
scale. Then for $X \ge M$

$$P(\text{repay } X \mid \text{largest repaid } M) = (1 - q)\left(\frac{M}{X}\right)^{a},$$

and if the evidence is $\tau$ old it applies with probability $\gamma^{\tau}$ (section 2), otherwise the
borrower is a fresh draw known only to have $c \ge x_{\min}$ (`ladder.repay_probability`; checked by Monte
Carlo).

## 5. How big can the next loan be?

A lender who accepts a default probability $\rho$ on each loan can let the amount due grow to at most

$$k_{\text{screen}} = \left(\frac{1 - q}{1 - \rho}\right)^{1/a}$$

times the largest amount repaid. This is progressive lending, with the step size derived from a risk
threshold instead of chosen. With $q = 0.02$, $\rho = 0.10$ and $a = 1$ it is 1.089: nine percent per step.
Doubling each time, at the same $q$ and $a$, means accepting $\rho = 0.51$.

That is the lender's side. Two more conditions come from the borrower's side, and they bound $k$ from below
and from above.

- **Honest borrowers must want to stay.** On a ladder growing by $k$, with interest $i$, a surplus $\sigma$
  per unit borrowed and discount rate $r$, staying is worth $\sigma P k / (1 + r - k)$ and leaving saves
  $P(1 + i)$. So repaying is rational iff

  $$k \;\ge\; k_{\text{stay}} = \frac{(1 + i)(1 + r)}{1 + i + \sigma}.$$

  The loan size $P$ cancels: this is the deterrent that scales, which reputation valued by dividends does
  not (`experiments/default_frontier`).
- **Climbing in order to default must not pay.** Someone with no use for the money who repays $n - 1$
  rungs and defaults on the last has paid interest $i \sum_{j<n} P_j$ to take $P_n$. For a long ladder the
  interest exceeds the take iff $k \le 1 + i$. At exactly $k = 1 + i$ the profit equals the first loan,
  whatever the length: **the first rung is the whole exposure**, so it must be small, bonded or vouched for.

Together: $k_{\text{stay}} \le k \le \min(k_{\text{screen}},\, 1 + i)$. With $i = r = 0.05$ and $\sigma = 0.03$ the
band is $[1.021,\, 1.05]$. It is non-empty exactly when

$$\sigma + i \;\ge\; r,$$

that is, when what the borrower earns on borrowed money covers their own discount rate. (`ladder.feasible_band`;
each bound is checked by direct summation in `tests/unit/test_ladder.py`.)

None of this needs a contract change. The promise log already records the amount, deadline and outcome of
every promise, so a lender or a script can compute $M$, $K$, $B$ and the next safe loan from it.

## 6. What is established and what is not

| claim | status |
|---|---|
| With hazard $h$, the mean estimate regresses to the prior at rate $\gamma = 1 - h$ | Derived, exact. |
| Decayed counts are the geometric pooling of posterior and prior | Derived, exact for Beta; checked numerically. |
| Decayed counts predict nearly as well as the exact filter | Measured on synthetic data from the model: 82 to 97% of the gap, at the best $\gamma$. |
| The best decay is faster than $h$, roughly $\propto \sqrt{h}$ | Observed at three hazards; explanation post hoc. |
| Largest amount repaid is the right statistic; the three bounds on $k$ | Derived from the threshold model and checked against it. Whether borrowers have such thresholds, and what $a$, $q$ and $\sigma$ are, is not established. |
| The two models combine | Not done. Section 1 to 3 model unreliable people, section 4 to 5 strategic ones. A joint model (a threshold that drifts, plus shocks) is the natural next step. |

The models are also silent on collusion: a lender and borrower who are the same person can manufacture any
record they like, at the cost of the fees. That is what the fee is for.
