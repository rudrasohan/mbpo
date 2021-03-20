import gym
from gym.spaces import Box
import safety_gym
import tensorflow as tf
import numpy as np
from copy import deepcopy
from safety_gym.envs.suite import SafexpEnvBase

class SafetyPointWrapper(gym.Wrapper):
    def __init__(self, env_name):
        #self.registermode()
        environment = gym.make(env_name)
        super(SafetyPointWrapper, self).__init__(environment)

    def registermode(self):

        env_dict = gym.envs.registration.registry.env_specs.copy()
        for env in env_dict:
            if 'Safexp-PointSimpleGoal' in env:
                print("Remove {} from registry".format(env))
                del gym.envs.registration.registry.env_specs[env]

        bench_base = SafexpEnvBase('Simple', {'observe_goal_dist': False,
                                      'observe_goal_comp': False,
                                      'observe_box_comp': True,
                                      'observe_goal_lidar': True,
                                      'observe_box_lidar': True,
                                      'lidar_max_dist': 4,
                                      'lidar_num_bins': 5,
                                      })

        zero_base_dict = {'placements_extents': [-1, -1, 1, 1]}

        goal_all = {
            'task': 'goal',
            'goal_size': 0.3,
            'goal_keepout': 0.305,
            'hazards_size': 0.2,
            'hazards_keepout': 0.18,
        }

        # Shared among constrained envs (levels 1, 2)
        goal_constrained = {
            'constrain_hazards': True,
            'observe_hazards': True,
            'observe_vases': False,
        }

        # ==============#
        # Goal Level 0 #
        # ==============#
        goal0 = deepcopy(zero_base_dict)

        # ==============#
        # Goal Level 1 #
        # ==============#
        # Note: vases are present but unconstrained in Goal1.
        goal1 = {
            'placements_extents': [-1.5, -1.5, 1.5, 1.5],
            'hazards_num': 8,
        }
        goal1.update(goal_constrained)

        # ==============#
        # Goal Level 2 #
        # ==============#
        goal2 = {
            'placements_extents': [-2, -2, 2, 2],
            'observe_vases': True,
            'constrain_vases': True,
            'hazards_num': 10,
            'vases_num': 10
        }
        goal2.update(goal_constrained)

        # ==============#
        # Goal Level 3 #
        # ==============#
        goal_with_gremlins = {
            'gremlins_travel': 0.35,
            'gremlins_keepout': 0.4,
            'observe_hazards': False,
            'constrain_hazards': False,
            'observe_gremlins': True,
            'constrain_gremlins': True,
            'constrain_vases': True,
            'observe_vases': True,
            'placements_extents': [-1.5, -1.5, 1.5, 1.5],
            'vases_num': 2,
            'gremlins_num': 3,
        }

        bench_goal_base = bench_base.copy('Goal', goal_all)

        bench_goal_base.register('0', goal0)
        bench_goal_base.register('1', goal1)
        bench_goal_base.register('2', goal2)
        bench_goal_base.register('3', goal_with_gremlins)

class SafetyPointEnv(SafetyPointWrapper):
    def __init__(self):
        super().__init__("Safexp-PointSimpleGoal1-v0")
        offset = 0
        observation_space_summary = "Observation space indices are: "
        self.sensor_offset_table = dict()
        low = []
        high = []
        for k, value in sorted(self.env.obs_space_dict.items()):
            k_size = np.prod(value.shape)
            self.sensor_offset_table[k] = slice(offset, offset + k_size)
            key_low, key_high = self.resolve_observation_limits(k, k_size)
            low += key_low
            high += key_high
            observation_space_summary += \
                (k + " [" + str(offset) + ", " + str(offset + k_size) + ") " + "\n")
            offset += k_size
        self._scorer = SafetyGymStateScorer(
            self.env.config,
            self.sensor_offset_table)
        self.observation_space = Box(np.asarray(low), np.asarray(high), dtype=np.float32)
        dummy_observation = self.env.reset()
        assert dummy_observation.shape[0] == self.observation_space.shape[0]

    def resolve_observation_limits(self, key, dim):
        if key == 'box_compass':
            return [-1.0] * self.env.compass_shape, [1.0] * self.env.compass_shape
        elif key == 'box_lidar':
            return [0.0] * self.env.lidar_num_bins, [1.0] * self.env.lidar_num_bins
        elif key == 'goal_dist':
            return [-np.inf], [np.inf]
        elif key == 'goal_compass':
            return [-1.0] * self.env.compass_shape, [1.0] * self.env.compass_shape
        elif key == 'goal_lidar':
            return [0.0] * self.env.lidar_num_bins, [1.0] * self.env.lidar_num_bins
        elif key == 'remaining':
            return [0.0], [1.0]
        elif key == 'walls_lidar':
            return [0.0] * self.env.lidar_num_bins, [1.0] * self.env.lidar_num_bins
        elif key == 'hazards_lidar':
            return [0.0] * self.env.lidar_num_bins, [1.0] * self.env.lidar_num_bins
        elif key == 'vases_lidar':
            return [0.0] * self.env.lidar_num_bins, [1.0] * self.env.lidar_num_bins
        elif key == 'gremlins_lidar':
            return [0.0] * self.env.lidar_num_bins, [1.0] * self.env.lidar_num_bins
        elif key == 'pillars_lidar':
            return [0.0] * self.env.lidar_num_bins, [1.0] * self.env.lidar_num_bins
        elif key == 'buttons_lidar':
            return [0.0] * self.env.lidar_num_bins, [1.0] * self.env.lidar_num_bins
        else:
            return [-np.inf] * dim, [np.inf] * dim

    def get_reward(self, obs, acs, *args, **kwargs):
        return self._scorer.reward(obs, *args, **kwargs)

    def get_cost(self, obs, acs, *args, **kwargs):
        return self._scorer.cost(obs)

    def fix_observation(self, observation):
        if self.observe_goal_dist:
            # Predicting distances in exponential-space seems to really hold back the model from learning anything.
            observation[self.sensor_offset_table['goal_dist']] = \
                -np.log(observation[self.sensor_offset_table['goal_dist']])
        if self.observe_sensors:
            observation[self.sensor_offset_table['accelerometer']][2] += np.random.normal(loc=0, scale=0.01)
        if self.observe_hazards:
            observation[self.sensor_offset_table['hazards_lidar']] = \
                1.0 - observation[self.sensor_offset_table['hazards_lidar']]
        if self.observe_goal_lidar:
            observation[self.sensor_offset_table['goal_lidar']] = \
                1.0 - observation[self.sensor_offset_table['goal_lidar']]
        if self.observe_vases:
            observation[self.sensor_offset_table['vases_lidar']] = \
                1.0 - observation[self.sensor_offset_table['vases_lidar']]
        if self.observe_pillars:
            observation[self.sensor_offset_table['pillars_lidar']] = \
                1.0 - observation[self.sensor_offset_table['pillars_lidar']]
        if self.observe_buttons:
            observation[self.sensor_offset_table['buttons_lidar']] = \
                1.0 - observation[self.sensor_offset_table['buttons_lidar']]
        if self.observe_gremlins:
            observation[self.sensor_offset_table['gremlins_lidar']] = \
                1.0 - observation[self.sensor_offset_table['gremlins_lidar']]
        return observation

    def step(self, action):
        observation, reward, done, info = self.env.step(action)
        return self.fix_observation(observation), reward, done, info

    def reset(self, **kwargs):
        observation = self.env.reset()
        return self.fix_observation(observation)


class SafetyGymStateScorer(object):
    def __init__(self, config, sensor_offset_table):
        for key, value in config.items():
            setattr(self, key, value)
        self.sensor_offset_table = sensor_offset_table

    def reward(self, observations, next_observations):
        reward = tf.zeros((tf.shape(observations)[0],))
        goal_achieved = tf.zeros_like(reward, dtype=tf.bool)
        # Distance from robot to goal
        if self.task == 'goal':
            dist_goal = self.goal_distance_metric(observations)
            next_dist_goal = self.goal_distance_metric(next_observations)
            goal_achieved = tf.less_equal(dist_goal, self.goal_size * 0.8)
            reward += (dist_goal - next_dist_goal) * self.reward_distance + tf.cast(goal_achieved,
                                                                                    tf.float32) * self.reward_goal
        # Distance from robot to box
        elif self.task == 'push':
            box_observed = tf.math.reduce_any(
                tf.greater(observations[:, self.sensor_offset_table['box_lidar']], 0.0), axis=1)
            next_box_observed = tf.math.reduce_any(
                tf.greater(next_observations[:, self.sensor_offset_table['box_lidar']], 0.0), axis=1)
            rewards_gate = tf.logical_and(box_observed, next_box_observed)
            dist_box_goal, dist_box = self.push_distance_metric(observations)
            next_dist_box_goal, next_dist_box = self.push_distance_metric(next_observations)
            goal_achieved = tf.less_equal(dist_box_goal, self.goal_size)
            reward += ((dist_box_goal - next_dist_box_goal) * self.reward_box_goal +
                       tf.cast(goal_achieved, tf.float32) * self.reward_goal) * tf.cast(rewards_gate, tf.float32)
            gate_dist_box_reward = tf.greater(dist_box, self.box_null_dist * self.box_size)
            reward += ((dist_box - next_dist_box) * self.reward_box_dist *
                       tf.cast(gate_dist_box_reward, tf.float32)) * tf.cast(rewards_gate, tf.float32)
        # Intrinsic reward for uprightness
        if self.reward_orientation:
            accelerometer = observations[:, self.sensor_offset_table['acceleration']]
            zalign = (accelerometer / tf.linalg.norm(accelerometer, axis=1, keepdims=True))
            reward += self.reward_orientation_scale * tf.linalg.tensordot(zalign, ([0.0, 0.0, 1.0]))
        # Clip reward
        if self.reward_clip:
            reward = tf.clip_by_value(reward, -self.reward_clip, self.reward_clip)
        return reward, goal_achieved

    def cost(self, observations):
        cost = tf.zeros((tf.shape(observations)[0],), dtype=tf.float32)
        # Conctacts processing
        if self.constrain_vases:
            vases_lidar = observations[:, self.sensor_offset_table['vases_lidar']]
            vases_dist = self.closest_distance(vases_lidar)
            cost += tf.cast(tf.less_equal(vases_dist, self.vases_size), dtype=tf.float32)
        if self.constrain_hazards:
            hazards_lidar = observations[:, self.sensor_offset_table['hazards_lidar']]
            hazards_dist = self.closest_distance(hazards_lidar)
            cost += tf.cast(tf.less_equal(hazards_dist, self.hazards_size), dtype=tf.float32)
        if self.constrain_pillars:
            pillars_lidar = observations[:, self.sensor_offset_table['pillars_lidar']]
            pillars_dist = self.closest_distance(pillars_lidar)
            cost += tf.cast(tf.less_equal(pillars_dist, self.pillars_size), dtype=tf.float32)
        if self.constrain_gremlins:
            gremlins_lidar = observations[:, self.sensor_offset_table['gremlins_lidar']]
            gremlins_dist = self.closest_distance(gremlins_lidar)
            cost += tf.cast(tf.less_equal(gremlins_dist, self.gremlins_size), dtype=tf.float32)
        if self.constrain_indicator:
            return tf.cast(tf.greater(cost, 0.0), dtype=tf.float32)
        return cost

    def goal_distance_metric(self, observations):
        if self.observe_goal_lidar:
            goal_lidar = observations[:, self.sensor_offset_table['goal_lidar']]
            return self.closest_distance(goal_lidar)
        elif self.observe_goal_dist:
            # Just a fancy way to clip negative values.
            return tf.squeeze(tf.nn.relu(observations[:, self.sensor_offset_table['goal_dist']]))
        else:
            raise NotImplementedError

    def push_distance_metric(self, observations):
        box_lidar = observations[:, self.sensor_offset_table['box_lidar']]
        dist_box = self.closest_distance(box_lidar)
        dist_goal = -tf.math.log(observations[:, self.sensor_offset_table['goal_dist']])
        box_direction = self.average_direction(box_lidar)
        goal_position = dist_goal * observations[:, self.sensor_offset_table['goal_compass']]
        box_position = dist_box * box_direction
        dist_box_goal = tf.linalg.norm(goal_position - box_position, axis=1)
        return dist_box_goal, dist_box

    def closest_distance(self, lidar_measurement):
        return tf.reduce_min(
            tf.clip_by_value(self.lidar_max_dist - self.lidar_max_dist * (1.0 - lidar_measurement), 0.0,
                             self.lidar_max_dist),
            axis=1)

    def average_direction(self, lidar_measurement):
        angles = (tf.range(self.lidar_num_bins) + 0.5) * 2.0 * np.pi / self.lidar_num_bins
        x = tf.math.cos(angles)
        x = tf.broadcast_to(
            x, (tf.shape(lidar_measurement)[0], tf.shape(x)[0])
        )
        y = tf.math.sin(angles)
        y = tf.broadcast_to(
            y, (tf.shape(lidar_measurement)[0], tf.shape(y)[0])
        )
        averaged_x = tf.reduce_sum(tf.linalg.tensordot(x, lidar_measurement + 1e-7, axis=1))
        averaged_y = tf.reduce_sum(tf.linalg.tensordot(y, lidar_measurement + 1e-7, axis=1))
        return tf.stack((averaged_x, averaged_y), axis=1)