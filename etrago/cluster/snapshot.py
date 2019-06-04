# -*- coding: utf-8 -*-
# Copyright 2016-2018  Flensburg University of Applied Sciences,
# Europa-Universität Flensburg,
# Centre for Sustainable Energy Systems


# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# File description for read-the-docs
""" This module contains functions for calculating representative days/weeks
based on a pyPSA network object. It is designed to be used for the `lopf`
method. Essentially the tsam package
( https://github.com/FZJ-IEK3-VSA/tsam ), which is developed by
Leander Kotzur is used.

Remaining questions/tasks:

- Does it makes sense to cluster normed values?
- Include scaling method for yearly sums
"""

import pandas as pd
import os
if 'READTHEDOCS' not in os.environ:
    import pyomo.environ as po
    import tsam.timeseriesaggregation as tsam

__copyright__ = ("Flensburg University of Applied Sciences, "
                 "Europa-Universität Flensburg, "
                 "Centre for Sustainable Energy Systems")
__license__ = "GNU Affero General Public License Version 3 (AGPL-3.0)"
__author__ = "Simon Hilpert"


def snapshot_clustering(network, resultspath, how='daily', clusters=[]):
    """
    """
    
    # original problem
    run(network=network.copy(), path=resultspath, write_results=write_results, n_clusters=None,
                  how=how, normed=False)
    
    for c in clusters:
        path=os.path.join(resultspath, how)
        run(network=network.copy(), path=path, write_results=write_results, n_clusters=c, 
            how=how, normed=False)

    return network, df_cluster


def tsam_cluster(timeseries_df, typical_periods=10, how='daily'):
    """
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with timeseries to cluster

    Returns
    -------
    timeseries : pd.DataFrame
        Clustered timeseries
    """

    if how == 'daily':
        hours = 24
    if how == 'weekly':
        hours = 168

    aggregation = tsam.TimeSeriesAggregation(
        timeseries_df,
        noTypicalPeriods=typical_periods,
        rescaleClusterPeriods=False,
        hoursPerPeriod=hours,
        clusterMethod='hierarchical')

    timeseries = aggregation.createTypicalPeriods()
    cluster_weights = aggregation.clusterPeriodNoOccur
    clusterOrder =aggregation.clusterOrder
    global clusterCenterIndices
    clusterCenterIndices= aggregation.clusterCenterIndices 
   
    # get all index for every hour of that day of the clusterCenterIndices
    start=[]  # get the first hour of the clusterCenterIndices (days start with 0)
    for i in clusterCenterIndices:
        start.append(i*hours)
    nrhours=[]  # get a list with all hours belonging to the clusterCenterIndices
    for j in start:
        nrhours.append(j)
        x=1
        while x < hours: 
            j=j+1
            nrhours.append(j)
            x=x+1
                
    # get the origial Datetimeindex
    dates = timeseries_df.iloc[nrhours].index 
    
    #get list of representative days   
    representative_day=[]
    dic_clusterCenterIndices = dict(enumerate(clusterCenterIndices)) #cluster:medoid des jeweiligen Clusters
    for i in clusterOrder: 
        representative_day.append(dic_clusterCenterIndices[i])
    #get list of last hour of representative days
    last_hour_datetime=[]
    for i in representative_day:
        last_hour = i*hours+hours-1
        last_hour_datetime.append(timeseries_df.index[last_hour])
    #create a dataframe (index=nr. of day in a year/candidate)
    df_cluster =  pd.DataFrame({
                        'Cluster': clusterOrder, #Cluster of the day
                        'RepresentativeDay': representative_day, #representative day of the cluster
                        'last_hour_RepresentativeDay': last_hour_datetime}) #last hour of the cluster  
    df_cluster.index = df_cluster.index + 1
    df_cluster.index.name = 'Candidate'
    
    #create a dataframe each timeseries (h) and its candiddate day (i) df_i_h
    nr_day = []
    x = len(timeseries_df.index)/hours+1
    
    for i in range(1,int(x)):
        j=1
        while j <= hours: 
            nr_day.append(i)
            j=j+1     
   
    global df_i_h
    df_i_h = pd.DataFrame({'Timeseries': timeseries_df.index, 
                        'Candidate_day': nr_day}) 
    df_i_h.set_index('Timeseries',inplace=True)
             
    return df_cluster, cluster_weights, dates, hours

def run(network, path, write_results=False, n_clusters=None, how='daily',
        normed=False):
    """
    """
    
    if n_clusters is not None:
        path=os.path.join(path, str(n_clusters))
        
        # reduce storage costs due to clusters
        network.cluster = True

        # calculate clusters
        df_cluster, cluster_weights, dates, hours = tsam_cluster(prepare_pypsa_timeseries(network),
                           typical_periods=n_clusters,
                           how='daily')       
        network.cluster = df_cluster
        update_data_frames(network, cluster_weights, dates, hours)   
        
    else:
        network.cluster=False
        path=os.path.join(path, 'original')
        
        snapshots=network.snapshots
        
        network_lopf(network, snapshots, extra_functionality=snapshots_cluster_constraints,
                     solver_name='gurobi', solver_options={'BarConvTol': 1.e-5, 'FeasibilityTol': 1.e-5, 'threads':4, 'method':2, 'crossover':0})
               
    if write_results:
        results_to_csv(network, path)
        write_lpfile(network, path=os.path.join(path, 'file.lp'))
    
    return network, df_cluster


def prepare_pypsa_timeseries(network, normed=False):
    """
    """

    if normed:
        normed_loads = network.loads_t.p_set / network.loads_t.p_set.max()
        normed_loads.columns = 'L' + normed_loads.columns
        normed_renewables = network.generators_t.p_max_pu
        normed_renewables.columns = 'G' + normed_renewables.columns

        df = pd.concat([normed_renewables,
                        normed_loads], axis=1)
    else:
        loads = network.loads_t.p_set.copy()
        loads.columns = 'L' + loads.columns
        renewables = network.generators_t.p_set.copy()
        renewables.columns = 'G' + renewables.columns
        df = pd.concat([renewables, loads], axis=1)

    return df


def update_data_frames(network, cluster_weights, dates, hours):
    """ Updates the snapshots, snapshots weights and the dataframes based on
    the original data in the network and the medoids created by clustering
    these original data.

    Parameters
    -----------
    network : pyPSA network object
    cluster_weights: dictionary
    dates: Datetimeindex


    Returns
    -------
    network

    """
    network.snapshot_weightings = network.snapshot_weightings.loc[dates]
    network.snapshots = network.snapshot_weightings.index

    # set new snapshot weights from cluster_weights
    snapshot_weightings = []
    for i in cluster_weights.values():
        x = 0
        while x < hours:
            snapshot_weightings.append(i)
            x += 1
    for i in range(len(network.snapshot_weightings)):
        network.snapshot_weightings[i] = snapshot_weightings[i]   
    
    #put the snapshot in the right order
    network.snapshots=network.snapshots.sort_values()
    network.snapshot_weightings=network.snapshot_weightings.sort_index()

     
    return network

def snapshot_cluster_constraints(network, snapshots):
    """  
    Notes
    ------
    Adding arrays etc. to `network.model` as attribute is not required but has
    been done as it belongs to the model as sets for constraints and variables

    """

    #if network.cluster:
    sus = network.storage_units
    # take every first hour of the clustered days
    network.model.period_starts = network.snapshot_weightings.index[0::24]

    network.model.storages = sus.index
    
    if True:
    # TODO: replace condition by somthing like:
    # if network.cluster['intertemporal']: ?
        # somewhere get 1...365, e.g in network.cluster['candidates']
        # should be array-like DONE
        candidates = network.cluster.index.get_values()

        # create set for inter-temp constraints and variables
        network.model.candidates = po.Set(initialize=candidates,
                                          ordered=True)

        # create intra soc variable for each storage and each hour
        network.model.state_of_charge_intra = po.Var(
            sus.index, network.snapshots,
            within=po.NonNegativeReals) 
        
        def intra_soc_rule(m, s, p):
            """
            Sets the soc_intra of every first hour to zero
            """
            return (m.state_of_charge_intra[s, p] == 0)
    
        network.model.period_bound = po.Constraint(
            network.model.storages, network.model.period_starts, rule = intra_soc_rule)       
        
        # create inter soc variable for each storage and each candidate
        # (e.g. day of year for daily clustering) 
        network.model.state_of_charge_inter = po.Var(
            sus.index, network.model.candidates, 
            within=po.NonNegativeReals) 
        
    
        def inter_storage_soc_rule(m, s, i):
            """
            Define the state_of_charge_inter as the state_of_charge_inter of the day before minus the storage losses 
            plus the state_of_charge (intra) of the last hour of the representative day
            """
                       
        
            if i == network.model.candidates[-1]:
                expr = (m.state_of_charge_inter[s, i] ==
                 m.state_of_charge_inter[s, network.model.candidates[1]])
            else:
                expr = (
                    m.state_of_charge_inter[s, i + 1] ==
                    m.state_of_charge_inter[s, i] 
                    * (1 - network.storage_units.at[s, 'standing_loss'])**24
                    + m.state_of_charge_intra[s, network.cluster["last_hour_RepresentativeDay"][i]])
            return expr
        network.model.inter_storage_soc_constraint = po.Constraint(
            sus.index, network.model.candidates,
            rule=inter_storage_soc_rule)
        
        
# =============================================================================
#         def inter_storage_capacity_rule(m, s, i):
#             """
#             Limit the capacity of the storage for every hour of the candidate day
#             """
#             
#             return (
#                    m.state_of_charge_inter[s, i] 
#                    * (1 - network.storage_units.at[s,'standing_loss'])**24  
#                    + m.state_of_charge_intra[s, network.cluster['last_hour_RepresentativeDay'][i]] <=
#                     network.storage_units.at[s, 'max_hours'] * network.storage_units.at[s,'p_nom']
#                     ) 
#              
#         
#         network.model.inter_storage_capacity_constraint = po.Constraint(
# =============================================================================
# =============================================================================
#             sus.index, network.model.candidates,
#             rule = inter_storage_capacity_rule)
# =============================================================================
             
        
        #new definition of the state_of_charge used in pypsa
        def total_state_of_charge(m,s,h):
            
            return( m.state_of_charge[s,h] == m.state_of_charge_intra[s,h] + network.model.state_of_charge_inter[s,df_i_h['Candidate_day'][h]])                
            
            
        network.model.total_storage_constraint = po.Constraint(
                sus.index, network.snapshots, rule = total_state_of_charge)
        
              
        
def daily_bounds(network, snapshots):
    """ This will bound the storage level to 0.5 max_level every 24th hour.
    """
    
    sus = network.storage_units
    # take every first hour of the clustered days
    network.model.period_starts = network.snapshot_weightings.index[0::24]

    network.model.storages = sus.index

    def day_rule(m, s, p):
        """
        Sets the soc of the every first hour to the soc of the last hour
        of the day (i.e. + 23 hours)
        """
        return (
            m.state_of_charge[s, p] ==
            m.state_of_charge[s, p + pd.Timedelta(hours=23)])

    network.model.period_bound = po.Constraint(
        network.model.storages, network.model.period_starts, rule=day_rule)

       
####################################
def manipulate_storage_invest(network, costs=None, wacc=0.05, lifetime=15):
    # default: 4500 € / MW, high 300 €/MW
    crf = (1 / wacc) - (wacc / ((1 + wacc) ** lifetime))
    network.storage_units.capital_cost = costs / crf

def write_lpfile(network=None, path=None):
    network.model.write(path,
                        io_options={'symbolic_solver_labels': True})


def fix_storage_capacity(network, resultspath, n_clusters):  # "network" added
    path = resultspath.strip('daily')
    values = pd.read_csv(path + 'storage_capacity.csv')[n_clusters].values
    network.storage_units.p_nom_max = values
    network.storage_units.p_nom_min = values
    resultspath = 'compare-' + resultspath
